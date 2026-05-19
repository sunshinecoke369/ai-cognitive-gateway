"""
Memory 分层定义

系统支持 4 层记忆，各层相互隔离：

| 层 | 说明 | TTL | 用途 |
|-----|------|-----|------|
| session | 会话级 | 1 小时 | 临时上下文，用完即弃 |
| user | 用户级 | 永久 | 跨会话的长期记忆（当前行为） |
| agent | Agent 级 | 30 天 | 按 Agent 隔离的记忆 |
| governance | 治理级 | 永久 | 审计专用，只写不读 |

各层在 store.py 中通过 layer 参数隔离查询。
TTL 过期由 compress_expired() 定期清理。
"""

from enum import Enum


class MemoryLayer(str, Enum):
    SESSION = "session"
    USER = "user"
    AGENT = "agent"
    GOVERNANCE = "governance"

    @property
    def ttl_seconds(self) -> int | None:
        """各层 TTL（秒），None 表示永久保留。"""
        return {
            "session": 3600,           # 1 小时
            "user": None,               # 永久
            "agent": 86400 * 30,        # 30 天
            "governance": None,          # 永久
        }.get(self.value)

    @property
    def description(self) -> str:
        return {
            "session": "会话级记忆，1 小时后自动过期",
            "user": "用户级长期记忆，永久保留",
            "agent": "Agent 隔离记忆，30 天后自动过期",
            "governance": "治理审计专用，永久保留且只写不读",
        }.get(self.value, "")
