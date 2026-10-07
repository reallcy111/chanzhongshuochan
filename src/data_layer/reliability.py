"""
src/data_layer/reliability.py — 数据源可靠性基础设施

按 plan 决策 (skills-fluttering-hinton.md):
- 3 次重试 (1s → 2s → 4s 指数退避)
- 5min 熔断（连续 N 次失败后熔断）
- SQLite 当日缓存
- 支持 HTTP (urllib/requests) + subprocess (westock) 异常统一

为 5 个 wrapper 提供统一可靠性能力：
- with_retry 装饰器（指数退避）
- CircuitBreaker（per-source 熔断）
- Cache（SQLite 当日有效）
- 异常映射（WestockError → DataSourceError 体系）
"""

from __future__ import annotations

import functools
import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar

logger = logging.getLogger(__name__)
T = TypeVar("T")

CACHE_DIR = Path.home() / ".cache" / "chanzhongshuochan"
CACHE_DB = CACHE_DIR / "cache.db"


# ============================================================
# 异常类层级（所有数据源共用基类）
# ============================================================
class DataSourceError(Exception):
    """所有数据源异常的基类"""


class TransientError(DataSourceError):
    """可重试的瞬时错误（网络超时、限流、subprocess 失败）"""


class PermanentError(DataSourceError):
    """永久错误（参数错误、股票代码不存在、Markdown 格式变更）"""


class RateLimitError(TransientError):
    """触发熔断（HTTP 429 / 东财限流 / westock 频繁调用）"""


# ============================================================
# 重试装饰器（指数退避，无需 tenacity 依赖）
# ============================================================
def with_retry(
    max_attempts: int = 3,
    base_wait: float = 1.0,
    max_wait: float = 10.0,
    retry_on: tuple[type[BaseException], ...] = (TransientError,),
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """指数退避重试装饰器（1s → 2s → 4s）。

    Args:
        max_attempts: 最大尝试次数（含首次），默认 3
        base_wait: 起始等待秒数
        max_wait: 最大等待秒数
        retry_on: 触发重试的异常类型元组
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            attempt = 0
            while attempt < max_attempts:
                try:
                    return func(*args, **kwargs)
                except retry_on as e:
                    attempt += 1
                    if attempt >= max_attempts:
                        logger.warning(
                            "已达最大重试次数 %d，放弃 %s: %s",
                            max_attempts, func.__name__, e,
                        )
                        raise
                    wait = min(base_wait * (2 ** (attempt - 1)), max_wait)
                    logger.info(
                        "第 %d/%d 次重试 %s（%s），等待 %.1fs",
                        attempt + 1, max_attempts, func.__name__, e, wait,
                    )
                    time.sleep(wait)

        return wrapper

    return decorator


# ============================================================
# 熔断器（Circuit Breaker）
# ============================================================
class CircuitBreaker:
    """5min 熔断器（连续失败 N 次后熔断 M 秒）。

    状态机: closed → open → half-open → closed
    - closed: 正常通过
    - open: 直接拒绝
    - half-open: 允许一次探测，成功则回到 closed
    """

    def __init__(self, failure_threshold: int = 3, recovery_time: float = 300.0) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_time = recovery_time
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._state = "closed"

    def can_execute(self) -> bool:
        if self._state == "closed":
            return True
        if self._state == "open":
            if time.time() - self._last_failure_time > self.recovery_time:
                self._state = "half-open"
                logger.info("CircuitBreaker 进入 half-open 状态（探测）")
                return True
            return False
        return True  # half-open

    def record_success(self) -> None:
        if self._state != "closed":
            logger.info("CircuitBreaker 恢复 closed 状态")
        self._failure_count = 0
        self._state = "closed"

    def record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.time()
        if self._failure_count >= self.failure_threshold:
            self._state = "open"
            logger.warning(
                "CircuitBreaker 熔断（连续 %d 次失败），恢复时间 %.0fs",
                self._failure_count, self.recovery_time,
            )

    @property
    def state(self) -> str:
        return self._state


# 全局熔断器注册表（按 source name 区分）
_breakers: dict[str, CircuitBreaker] = {}


def get_breaker(source_name: str) -> CircuitBreaker:
    """获取或创建指定 source 的熔断器"""
    if source_name not in _breakers:
        _breakers[source_name] = CircuitBreaker()
    return _breakers[source_name]


def reset_all_breakers() -> None:
    """重置所有熔断器（测试用）"""
    _breakers.clear()


# ============================================================
# SQLite 当日缓存
# ============================================================
class Cache:
    """SQLite 当日缓存（key → JSON value，默认当天有效）。"""

    def __init__(self, db_path: Path = CACHE_DB) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    source TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_created
                ON cache(created_at)
            """)

    def get(self, key: str, today_only: bool = True) -> Optional[str]:
        """获取缓存值（None 表示 miss 或过期）"""
        with sqlite3.connect(str(self.db_path)) as conn:
            row = conn.execute(
                "SELECT value, created_at FROM cache WHERE key = ?",
                (key,),
            ).fetchone()
            if row is None:
                return None
            value, created_at = row
            if today_only:
                today = time.strftime("%Y-%m-%d")
                if not created_at.startswith(today):
                    conn.execute("DELETE FROM cache WHERE key = ?", (key,))
                    return None
            return value

    def set(self, key: str, value: str, source: str = "") -> None:
        """设置缓存"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO cache (key, value, created_at, source)
                   VALUES (?, ?, ?, ?)""",
                (key, value, time.strftime("%Y-%m-%d %H:%M:%S"), source),
            )

    def clear_expired(self) -> int:
        """清理非今天的缓存，返回清理条数"""
        today = time.strftime("%Y-%m-%d")
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.execute(
                "DELETE FROM cache WHERE created_at NOT LIKE ?",
                (f"{today}%",),
            )
            return cursor.rowcount

    def clear_all(self) -> None:
        """清空所有缓存（测试用）"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("DELETE FROM cache")


_global_cache: Optional[Cache] = None


def get_cache() -> Cache:
    """获取全局缓存单例"""
    global _global_cache
    if _global_cache is None:
        _global_cache = Cache()
    return _global_cache


# ============================================================
# 缓存装饰器（高层便捷 API）
# ============================================================
def cached(
    source: str = "", today_only: bool = True
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """缓存装饰器（默认当日有效）。

    Args:
        source: 数据源名称（用于 key 前缀和调试）
        today_only: True=当日有效，False=永久（按 db_path 管理）
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            cache = get_cache()
            key_parts = [source or "default", func.__name__]
            key_parts.extend(str(a) for a in args)
            key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
            full_key = "|".join(key_parts)

            cached_value = cache.get(full_key, today_only=today_only)
            if cached_value is not None:
                logger.debug("缓存命中: %s", full_key)
                try:
                    return json.loads(cached_value)
                except json.JSONDecodeError:
                    logger.warning("缓存反序列化失败: %s", full_key)
            result = func(*args, **kwargs)
            try:
                cache.set(full_key, json.dumps(result, default=str), source)
            except (TypeError, ValueError) as e:
                logger.warning("缓存序列化失败 %s: %s", full_key, e)
            return result

        return wrapper

    return decorator


# ============================================================
# WestockError 映射（延迟导入避免循环引用）
# ============================================================
def classify_westock_error(exc: BaseException) -> DataSourceError:
    """把 westock 异常映射到统一 DataSourceError 体系。

    映射规则：
    - WestockEnvError → PermanentError（无 Node 不重试）
    - WestockTransientError → TransientError（subprocess 失败，可重试）
    - WestockPermanentError / WestockParseError → PermanentError
    - 未知异常 → PermanentError（保守策略）

    Returns:
        包装后的 DataSourceError（保留原始 exc 作为 __cause__）
    """
    try:
        from .westock_wrapper import (
            WestockEnvError,
            WestockTransientError,
            WestockPermanentError,
            WestockParseError,
        )
    except ImportError:
        return _wrap(PermanentError, exc, prefix="westock unavailable")


def _wrap(cls: type[DataSourceError], exc: BaseException, prefix: str = "") -> DataSourceError:
    """包装异常并保留 __cause__ 链。"""
    msg = f"{prefix}: {exc}" if prefix else str(exc)
    new_exc = cls(msg)
    new_exc.__cause__ = exc
    return new_exc

    if isinstance(exc, WestockEnvError):
        return _wrap(PermanentError, exc)
    if isinstance(exc, WestockTransientError):
        return _wrap(TransientError, exc)
    if isinstance(exc, (WestockPermanentError, WestockParseError)):
        return _wrap(PermanentError, exc)
    return _wrap(PermanentError, exc, prefix="westock unknown error")


# ============================================================
# 自检（命令行）
# ============================================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    # 测试重试
    @with_retry(max_attempts=3, base_wait=0.1)
    def flaky_func(fail_times: int = 2) -> str:
        if flaky_func.attempts < fail_times:  # type: ignore[attr-defined]
            flaky_func.attempts += 1  # type: ignore[attr-defined]
            raise TransientError(f"模拟失败 #{flaky_func.attempts}")  # type: ignore[attr-defined]
        return "ok"
    flaky_func.attempts = 0  # type: ignore[attr-defined]

    print("测试重试:", flaky_func(fail_times=2))

    # 测试熔断
    breaker = CircuitBreaker(failure_threshold=2, recovery_time=2.0)
    for i in range(3):
        if breaker.can_execute():
            breaker.record_failure()
            print(f"  失败 #{i+1}, 状态={breaker.state}")
        else:
            print(f"  跳过 #{i+1}, 状态={breaker.state}")

    # 测试缓存
    cache = get_cache()
    cache.set("test_key", json.dumps({"data": "hello"}), "test")
    print("缓存读取:", cache.get("test_key"))

    print("[OK] reliability.py self-check passed")