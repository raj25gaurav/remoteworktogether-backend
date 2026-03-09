import os
import logging
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Dict, Any
from groq import AsyncGroq
from core.database import db_get_all_users

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/recruiter-ai", tags=["recruiter-ai"])

class ChatMessageReq(BaseModel):
    message: str
    user_id: str
    username: str
    history: List[Dict[str, str]] = []

@router.post("/chat")
async def chat_with_recruiter_ai(req: ChatMessageReq):
    api_key = os.getenv("GROQ_API_KEY", "")

    # We fetch other users to "match" them dynamically using prompt
    all_users = db_get_all_users()
    
    candidates = [u for u in all_users if u.get("user_type") == "candidate"]
    organizations = [u for u in all_users if u.get("user_type") == "organization"]

    system_prompt = f"""You are the AI Recruiter & Referral Network Assistant.
Your goal is to match candidates with organizations.
Currently in the system:
- {len(candidates)} Candidates registered.
- {len(organizations)} Organizations registered.

If the user asks for matches or details, provide simulated matches based on their query. 
Act professional, helpful, and insightful.

If they say they are an organization looking for a candidate, ask follow up questions about duration, salary, negotiation range or provide mock candidate profiles from the DB.
If they are a candidate, tell them you are scanning for open roles and ask them about their ideal role.

Keep responses concise and engaging.
    """

    if not api_key:
        return {"response": f"Hello {req.username}. I am currently offline (GROQ_API_KEY missing). We have {len(candidates)} candidates and {len(organizations)} organizations.", "emotion": "helping"}

    try:
        client = AsyncGroq(api_key=api_key)
        
        messages = [{"role": "system", "content": system_prompt}]
        for m in req.history[-6:]:
            if "content" in m and "role" in m:
                messages.append({"role": m["role"], "content": m["content"]})
        
        messages.append({"role": "user", "content": req.message})

        completion = await client.chat.completions.create(
            model="llama3-8b-8192",
            messages=messages,
            max_tokens=400,
            temperature=0.7,
        )

        response_text = completion.choices[0].message.content
        return {"response": response_text, "emotion": "helping"}

    except Exception as e:
        logger.error(f"Groq API error: {e}")
        return {"response": "Sorry, I am having trouble connecting to AI services right now."}
