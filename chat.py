from dotenv import load_dotenv

load_dotenv()

import os
import json
import requests
import PyPDF2
import streamlit as st
from io import BytesIO
from datetime import datetime
from supabase import create_client
from openai import OpenAI

client = OpenAI()

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
supabase = create_client(url, key)


def log_message(message):
    if "log_history" not in st.session_state:
        st.session_state.log_history = []
    st.session_state.log_history.append(message)

    # Update the logs placeholder dynamically
    st.session_state.logs_placeholder.text("\n".join(st.session_state.log_history))


def get_chat_history(user_id, session_id):
    filename = f"chat_{user_id}_{session_id}.json"
    try:
        with open(filename, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_chat_history(user_id, session_id, messages):
    filename = f"chat_{user_id}_{session_id}.json"
    with open(filename, "w") as f:
        json.dump(messages, f, indent=2)


def store_message(user_id, session_id, message):
    messages = get_chat_history(user_id, session_id)
    messages.append(message)
    save_chat_history(user_id, session_id, messages)


def call_agent(chat_history, tools):
    return (
        client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.1,
            messages=chat_history,
            tools=tools,
            tool_choice="auto",
        )
        .choices[0]
        .message
    )


def summarize_pdf(input):
    try:
        response = requests.get(input["pdf_url"])
        response.raise_for_status()

        pdf_file = BytesIO(response.content)
        reader = PyPDF2.PdfReader(pdf_file)
        text = " ".join(
            [page.extract_text() for page in reader.pages if page.extract_text()]
        )

        if not text.strip():
            return {"error": "Could not extract text from PDF."}

        summary = (
            client.chat.completions.create(
                model="gpt-4o-mini",
                temperature=0.3,
                messages=[
                    {
                        "role": "system",
                        "content": "Summarize the PDF content concisely.",
                    },
                    {"role": "user", "content": text[:100000]},  # Limit input size
                ],
            )
            .choices[0]
            .message.content
        )

        return {"summary": summary}

    except Exception as e:
        return {"error": str(e)}


def generate_query_with_llm(input):
    system_prompt = """You are an assistant that generates Supabase queries in Python.
    You must only generate queries that read data.
    Do not generate any other types of queries like INSERT, UPDATE, or DELETE.
    - Example:
      Input: {"gr_no": "1234", "date": "2024-01", "branch": "Finance"}
      Output:
      query = supabase.table("documents").select("*").ilike("gr_no", "%1234%").gte("date", "2024-01-01").lt("date", "2024-02-01").ilike("branch", "%Finance%")
    - If filtering by "date", always use `gte("date", "YYYY-MM-DD")` and `lt("date", "YYYY-MM-DD")` for the end of the month.
    - If filtering by "gr_no", "branch", "subject_en" and "subject_gu", always use `ilike("gr_no", "%search_term%")`, `ilike("branch", "%search_term")`, `ilike("subject_en", "%search_term%")` and `ilike("subject_gu", "%search_term%")`.
    Return only the Python code for the SELECT query (no explanations).
    """

    user_prompt = f"Generate a Supabase query for this input: {input}"

    response = (
        client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
        )
        .choices[0]
        .message.content
    )

    if (
        not response.strip().lower().startswith("query = supabase.table")
        or "select" not in response.lower()
    ):
        raise ValueError(
            "Only SELECT queries are allowed. Query generated is not a SELECT query."
        )

    return response


def get_pdf_related_data(input):
    try:
        log_message("Generating the query...")
        query_code = generate_query_with_llm(input)
        print(f"  {query_code}")

        if "select(" not in query_code:
            return {"error": "Only SELECT queries are allowed"}

        log_message("Fetching data...")
        exec(query_code, globals())
        response = query.execute()

        if response and hasattr(response, "data"):
            log_message(f"  Query successful, retrieved {len(response.data)} records.")
            return {"results": response.data}
        else:
            log_message("  Query returned an unexpected response.")
            return {"error": "Unexpected response format"}

    except Exception as e:
        log_message(f"Error occurred: {e}")
        return {"error": str(e)}


def call_tool(tool_call):
    try:
        log_message("Detecting the arguments...")
        args = json.loads(tool_call.function.arguments)
        print(f"  {args}")
        tool_name = tool_call.function.name

        if tool_name == "get_pdf_related_data":
            return get_pdf_related_data(args)
        elif tool_name == "summarize_pdf":
            return summarize_pdf(args)

        return {"error": "Unknown tool"}
    except json.JSONDecodeError:
        return {"error": "Invalid arguments format"}


def run_agent(user_id, session_id, user_message):
    now = datetime.now()
    log_message("Generating the response...")

    system_prompt = f"""
        You are an AI assistant for querying and summarizing financial department documents. When you receive data from a tool call (presented as a 'tool' message in the conversation), please use that information to provide a complete answer. If the tool returns a list of documents, list them in your answer. If the query is ambiguous, ask clarifying questions.
        <context>
            Current time: {now.strftime("%H:%M:%S %d-%m-%Y")} 
        </context>
    """

    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_pdf_related_data",
                "description": "Query database for PDFs using various criteria. Maintain the original language as input.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "gr_no": {
                            "type": "string",
                            "description": "GR number e.g. STS-1096-535-Adt.07-03-1996, FD/OTH/e-file/4/2024/Extended Budget, જનવ-૧૦૨૦૧૪-૪૭૩૯૦૨-(૨)-અ",
                        },
                        "date": {
                            "type": "string",
                            "description": "Date/Year e.g. 12/06/2005, 2023, Jan 2019. For a range, use 'from_date' and 'to_date' instead.",
                        },
                        "from_date": {
                            "type": "string",
                            "description": "Start date e.g. 2023-01-01",
                        },
                        "to_date": {
                            "type": "string",
                            "description": "End date e.g. 2023-12-31",
                        },
                        "branch": {
                            "type": "string",
                            "enum": [
                                "A-(Public Sector Undertaking)",
                                "CH-(Service Matter)",
                                "K-(Budget)",
                                "M-(Pay of Government Employee)",
                                "PayCell-(Pay Commission)",
                                "N-(Banking)",
                                "P-(Pension)",
                                "T-(Local Establishment)",
                                "TH-(Value Added Tax)",
                                "TH-3-(Commercial Tax Establishment)",
                                "Z-(Treasury)",
                                "Z-1-(Economy)",
                                "G-(Audit Para)",
                                "GH-(Accounts Cadre Establishment)",
                                "FR-(Financial Resources)",
                                "DMO-(Debt Management)",
                                "GO Cell-(Government Companies)",
                                "B-RTI Cell-(Small Savings RTI)",
                                "KH",
                                "PMU-Cell",
                                "GST Cell",
                            ],
                            "description": "Branch name",
                        },
                        "subject_en": {
                            "type": "string",
                            "description": "Document subject in English e.g. 'Payment of bonus for the year 2016-17 to Class-4 employees of the Government of Gujarat'. If the subject is in Gujarati, use 'subject_gu' instead.",
                        },
                        "subject_gu": {
                            "type": "string",
                            "description": "Document subject in Gujarati. If the subject is in English, use 'subject_en' instead.",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "summarize_pdf",
                "description": "Summarize PDF content from URL",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pdf_url": {"type": "string", "description": "PDF URL"}
                    },
                    "required": ["pdf_url"],
                },
            },
        },
    ]

    messages = get_chat_history(user_id, session_id)
    store_message(user_id, session_id, user_message)

    while True:
        messages = get_chat_history(user_id, session_id)
        messages.insert(0, {"role": "system", "content": system_prompt})
        response = call_agent(messages, tools)

        assistant_msg = response.model_dump()
        store_message(user_id, session_id, assistant_msg)

        if response.content:
            st.session_state.final_response = response.content
            return response.content

        if response.tool_calls:
            for tool_call in response.tool_calls:
                tool_response = call_tool(tool_call)

                store_message(
                    user_id,
                    session_id,
                    {
                        "role": "tool",
                        "content": json.dumps(tool_response),
                        "tool_call_id": tool_call.id,
                    },
                )
        st.session_state.logs_placeholder = st.empty()


if __name__ == "__main__":
    user_id = "test_user"
    session_id = "session_1"
    user_message = {
        "role": "user",
        "content": "પીએફઆર-૧૦૭૧-૮૮૦-ચ",
    }

    response = run_agent(user_id, session_id, user_message)
    print("Final Response:", response)
