"""
Chat/Conversational assistant API endpoints
"""
from fastapi import APIRouter, HTTPException
import uuid
import logging

from ..models.schemas import ChatRequest, ChatResponse
from ..services.gpt5_service import gpt5_service
from ..services.neo4j_service import neo4j_service
from ..config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

# Simple in-memory conversation storage (use Redis in production)
conversations = {}


@router.post("/", response_model=ChatResponse)
async def chat_with_assistant(request: ChatRequest):
    """
    Chat with the RCA assistant

    The assistant can:
    - Answer questions about your infrastructure
    - Explain failures and suggest fixes
    - Guide you through troubleshooting
    - Provide kubectl commands

    Example:
    ```json
    {
      "message": "What's causing high memory usage in the auth service?",
      "client_id": "ab-01",
      "reasoning_effort": "low"
    }
    ```
    """
    try:
        client_id = request.client_id or settings.default_client_id
        conversation_id = request.conversation_id or str(uuid.uuid4())

        logger.info(f"Chat request: {request.message[:100]}")

        # Get conversation history
        conversation_history = conversations.get(conversation_id, [])

        # Get context if event IDs provided
        context_data = None
        if request.context_events:
            context_data = {
                "events": []
            }
            for event_id in request.context_events[:5]:  # Limit context
                chain = neo4j_service.find_causal_chain(
                    event_id=event_id,
                    client_id=client_id,
                    max_hops=2
                )
                if chain:
                    context_data["events"].append({
                        "event_id": event_id,
                        "causal_chain": chain
                    })

        # Call GPT-5 assistant
        response = gpt5_service.chat_assistant(
            message=request.message,
            context_data=context_data,
            conversation_history=conversation_history,
            reasoning_effort=request.reasoning_effort.value
        )

        # Update conversation history
        conversation_history.append({"role": "user", "content": request.message})
        conversation_history.append({"role": "assistant", "content": response["message"]})

        # Keep last 10 messages
        conversations[conversation_id] = conversation_history[-10:]

        # Generate suggested queries
        suggested_queries = _generate_suggestions(request.message, response["message"])

        # Extract any event mentions from context
        related_events = request.context_events or []

        return ChatResponse(
            message=response["message"],
            conversation_id=conversation_id,
            suggested_queries=suggested_queries,
            related_events=related_events,
            confidence=response.get("confidence", 0.7),
            reasoning_summary=response.get("reasoning_summary")
        )

    except Exception as e:
        logger.error(f"Chat failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")


@router.delete("/conversations/{conversation_id}")
async def clear_conversation(conversation_id: str):
    """
    Clear a conversation history
    """
    if conversation_id in conversations:
        del conversations[conversation_id]
        return {"status": "success", "message": "Conversation cleared"}
    else:
        raise HTTPException(status_code=404, detail="Conversation not found")


@router.get("/conversations/{conversation_id}")
async def get_conversation_history(conversation_id: str):
    """
    Get conversation history
    """
    if conversation_id not in conversations:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return {
        "conversation_id": conversation_id,
        "messages": conversations[conversation_id],
        "message_count": len(conversations[conversation_id])
    }


def _generate_suggestions(user_message: str, assistant_response: str) -> List[str]:
    """
    Generate suggested follow-up queries
    """
    suggestions = []

    # Common follow-ups
    if "error" in user_message.lower() or "fail" in user_message.lower():
        suggestions.extend([
            "How can I fix this?",
            "Show me the blast radius",
            "What caused this failure?"
        ])
    elif "how" in user_message.lower():
        suggestions.extend([
            "Can you show me an example?",
            "What are the best practices?",
            "Are there any alternatives?"
        ])
    elif "why" in user_message.lower():
        suggestions.extend([
            "Show me related events",
            "What's the root cause?",
            "How can I prevent this?"
        ])
    else:
        suggestions.extend([
            "Tell me more",
            "Show me examples",
            "What else should I know?"
        ])

    return suggestions[:3]
