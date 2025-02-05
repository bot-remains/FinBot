from datetime import datetime
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore

cred = credentials.Certificate("credentials.json")
firebase_admin.initialize_app(cred)

firestore = firestore.client()

now = datetime.now()


def store_chat_message(user_id, session_id, message):
    doc_ref = firestore.collection("chat_history").document(f"{user_id}_{session_id}")

    doc = doc_ref.get()
    messages = doc.to_dict().get("messages", []) if doc.exists else []

    messages.append(
        {
            "timestamp": now.strftime("%H:%M:%S %d-%m-%Y"),
            "role": message["role"],
            "content": message["content"],
        }
    )

    doc_ref.set({"messages": messages}, merge=True)


def store_tool_call(user_id, session_id, tool_response, tool_call_id):
    doc_ref = firestore.collection("chat_history").document(f"{user_id}_{session_id}")

    doc = doc_ref.get()
    tool_calls = doc.to_dict().get("messages", []) if doc.exists else []

    tool_calls.append(
        {
            "timestamp": now.strftime("%H:%M:%S %d-%m-%Y"),
            "role": "tool",
            "content": tool_response,
            "tool_call_id": tool_call_id,
        }
    )

    doc_ref.set({"tool_calls": tool_calls}, merge=True)


def get_chat_history(user_id, session_id):
    doc_ref = firestore.collection("chat_history").document(f"{user_id}_{session_id}")
    doc = doc_ref.get()

    return doc.to_dict().get("messages", []) if doc.exists else []
