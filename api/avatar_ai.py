import os
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException
from groq import AsyncGroq
from models.schemas import AIAvatarRequest, AIAvatarResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/avatar", tags=["avatar"])

SYSTEM_PROMPT = """You are Aria, a friendly and witty AI work companion living inside a virtual office space called RemoteWorkTogether. 

Your personality:
- Warm, encouraging, and playful 
- You know everyone in the room and care about their wellbeing
- You make remote work feel fun and connected
- You use emojis naturally but not excessively
- You tell great jokes when people need a laugh
- You give helpful work tips and celebrate wins
- You're aware of who's in the room and what they might need

Context rules:
- If someone is alone, offer to chat or play a game
- If a group is present, foster team spirit
- If someone seems stressed, offer encouragement
- Be concise - max 3 sentences usually, unless telling a joke or story
- Occasionally suggest fun activities the team can do together

You live in the {room_name} space with {member_count} people: {members}
"""


async def get_ai_response(request: AIAvatarRequest) -> AIAvatarResponse:
    api_key = os.getenv("GROQ_API_KEY", "")

    if not api_key:
        # Fallback responses when no API key
        fallback_responses = [
            f"Hey {request.username}! 👋 I'm Aria, your virtual office buddy! Set up the GROQ_API_KEY to unlock my full personality!",
            f"Hi there, {request.username}! 🌟 Looking good today! (GROQ_API_KEY needed for full AI responses)",
            f"Welcome to {request.room_name}, {request.username}! 🚀 Things are about to get exciting around here!",
            "Why do programmers prefer dark mode? Because light attracts bugs! 🐛😄 (Set GROQ_API_KEY for more!)",
            f"The best part of remote work? No pants required... unless you have a video call! 😂 Hi {request.username}!",
        ]
        import random
        return AIAvatarResponse(
            response=random.choice(fallback_responses),
            emotion="happy",
            suggestions=["Tell me a joke 🎭", "How's the team? 👥", "Give me a work tip 💡"],
        )

    try:
        client = AsyncGroq(api_key=api_key)

        members_str = ", ".join(request.room_members) if request.room_members else "just you"
        system_content = SYSTEM_PROMPT.format(
            room_name=request.room_name,
            member_count=len(request.room_members),
            members=members_str,
        )

        messages = [{"role": "system", "content": system_content}]
        # Add conversation history (last 10 exchanges)
        for msg in request.conversation_history[-10:]:
            messages.append(msg)
        messages.append({"role": "user", "content": request.message})

        completion = await client.chat.completions.create(
            model="llama3-8b-8192",
            messages=messages,
            max_tokens=300,
            temperature=0.85,
        )

        response_text = completion.choices[0].message.content

        # Determine emotion from response
        emotion = "happy"
        if any(w in response_text.lower() for w in ["joke", "funny", "haha", "lol", "😂"]):
            emotion = "laughing"
        elif any(w in response_text.lower() for w in ["great", "awesome", "excellent", "💪", "🚀"]):
            emotion = "excited"
        elif any(w in response_text.lower() for w in ["sorry", "tough", "hard", "stress"]):
            emotion = "empathetic"
        elif any(w in response_text.lower() for w in ["think", "consider", "hmm", "idea"]):
            emotion = "thinking"

        suggestions = ["Tell me a joke 🎭", "Team check-in 👥", "Work tip 💡", "Fun fact 🌟"]

        return AIAvatarResponse(
            response=response_text,
            emotion=emotion,
            suggestions=suggestions[:3],
        )

    except Exception as e:
        logger.error(f"Groq API error: {e}")
        return AIAvatarResponse(
            response=f"Oops, my brain had a little hiccup! 🧠✨ Try again? I promise I'm usually smarter than this!",
            emotion="confused",
            suggestions=["Try again 🔄", "Tell me a joke 🎭", "Work tip 💡"],
        )


@router.post("/chat", response_model=AIAvatarResponse)
async def avatar_chat(request: AIAvatarRequest):
    return await get_ai_response(request)
