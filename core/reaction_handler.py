import logging
import random
from typing import Optional
from models.schemas import Reaction

logger = logging.getLogger(__name__)

# Popular emoji categories for quick reactions
QUICK_REACTIONS = ["👍", "❤️", "😂", "😮", "😢", "🎉", "🔥", "💯", "🙌", "✨"]
WORK_EMOJIS = ["💻", "☕", "📊", "🚀", "💡", "📝", "🎯", "⚡", "🏆", "💪"]
FUN_EMOJIS = ["🎮", "🎸", "🍕", "🦄", "🌈", "🎪", "🎭", "🎨", "🎬", "🎤"]


class ReactionHandler:
    """Handles emoji and GIF reactions with animation data."""

    def create_reaction_payload(
        self,
        sender_id: str,
        username: str,
        content: str,
        room_id: str,
        reaction_type: str = "emoji",
        x: Optional[float] = None,
        y: Optional[float] = None,
    ) -> dict:
        """Create a reaction payload with random position if not specified."""
        return {
            "id": f"r_{sender_id}_{random.randint(1000, 9999)}",
            "sender_id": sender_id,
            "username": username,
            "type": reaction_type,
            "content": content,
            "room_id": room_id,
            "x": x if x is not None else random.uniform(10, 90),
            "y": y if y is not None else random.uniform(10, 80),
            "timestamp": __import__("time").time(),
            "animation": random.choice(["float-up", "spiral", "bounce", "spin"]),
            "size": random.choice(["sm", "md", "lg"]),
        }

    def get_quick_reactions(self) -> list:
        return QUICK_REACTIONS

    def get_work_emojis(self) -> list:
        return WORK_EMOJIS

    def get_fun_emojis(self) -> list:
        return FUN_EMOJIS
