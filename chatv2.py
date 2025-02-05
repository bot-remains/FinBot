from dotenv import load_dotenv

load_dotenv()

import os
import json
import httpx
import streamlit as st
import tiktoken
from datetime import datetime
import pytesseract
from pdf2image import convert_from_bytes
from supabase import create_client
from openai import OpenAI

client = OpenAI()
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
supabase = create_client(url, key)

if "log_history" not in st.session_state:
    st.session_state.log_history = []


def log_message(message):
    st.session_state.log_history.append(message)
    logs_placeholder.markdown(
        "\n".join(f"• {msg}\n" for msg in st.session_state.log_history)
    )


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


def summary_llm(text, prompt):
    response = (
        client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": text},
            ],
        )
        .choices[0]
        .message.content
    )
    return response


def summarize_pdf(input):
    try:
        log_message("Inside summarize_pdf")
        log_message("Fetching the PDF...")
        with httpx.Client() as client:
            response = client.get(input["pdf_url"])
            response.raise_for_status()

        pdf_binary = response.content

        images = convert_from_bytes(pdf_binary)

        log_message("Fetching successful.")

        encoding = tiktoken.encoding_for_model("gpt-4o-mini")
        text = ""
        summaries = []
        max_tokens = 100000

        log_message("Extracting the text...")
        for img in images:
            page_text = pytesseract.image_to_string(img, lang="eng+guj")
            if len(encoding.encode(text + page_text + "\n")) < max_tokens:
                text += page_text + "\n"
            else:
                summaries.append(
                    summary_llm(
                        text,
                        "Summarize the given content with all the important details.",
                    )
                )
                text = page_text + "\n"

        log_message("Summarizing the text...")
        if summaries:
            combined_summaries = "\n\n\n".join(summaries)
            final_summary = summary_llm(
                combined_summaries,
                "Given the summaries separated by three newlines, generate a final summary.",
            )
        else:
            final_summary = summary_llm(
                text, "Summarize the given content with all the important details."
            )

        return {"summary": final_summary}

    except Exception as e:
        return {"error": str(e)}


def query_pdf(input):
    try:
        log_message("Inside query_pdf")
        log_message("Fetching the PDF...")
        with httpx.Client() as client:
            response = client.get(input["pdf_url"])
            response.raise_for_status()

        pdf_binary = response.content

        images = convert_from_bytes(pdf_binary)

        log_message("Fetching successful.")

        text = ""

        log_message("Extracting the text...")
        for img in images:
            page_text = pytesseract.image_to_string(img, lang="eng+guj")
            text += page_text + "\n"

        log_message("Generating the answer...")
        response = (
            client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": f"Given the text from the pdf, generate an answer to the user query.\n Text: {text}",
                    },
                    {"role": "user", "content": input["query"]},
                ],
            )
            .choices[0]
            .message.content
        )

        return {"answer": response}

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
        log_message(f"```{query_code}```")

        if "select(" not in query_code:
            return {"error": "Only SELECT queries are allowed"}

        log_message("Fetching data...")
        exec(query_code, globals())
        response = query.execute()

        if response and hasattr(response, "data"):
            log_message(f"Query successful, retrieved {len(response.data)} records.")
            print(response.data)
            return {"results": response.data}
        else:
            log_message("  Query returned an unexpected response.")
            return {"error": "Unexpected response format"}

    except Exception as e:
        log_message(f"Error occurred: {e}")
        return {"error": str(e)}


def get_pdf_by_content(input):
    try:
        log_message("Generating the embeddings...")
        emb = client.embeddings.create(
            model="text-embedding-3-small", input=input["content"]
        )
        embedding = emb.data[0].embedding

        log_message("Searching for similar documents...")
        # data = supabase.rpc(
        #     "hybrid_search",
        #     {
        #         "query_text": input["content"],
        #         "query_embedding": embedding,
        #         "match_count": 10,
        #     },
        # ).execute()

        data = supabase.rpc(
            "match_documents",
            {"query_embedding": embedding, "match_threshold": 0.78, "match_count": 10},
        ).execute()

        return {"results": data.data}
    except Exception as e:
        log_message(f"Error occurred: {e}")
        return {"error": str(e)}


# def count_records(input):
#     try:
#         log_message("Generating the query...")
#         query_code = (
#             client.chat.completions.create(
#                 model="gpt-4o-mini",
#                 messages=[
#                     {
#                         "role": "system",
#                         "content": """You are an assistant that generates safe and valid Supabase queries in Python to count the number of records based on user input. Follow these rules:
#
# - **Only generate SELECT queries with a count.** **DO NOT** generate INSERT, UPDATE, DELETE, or any other operations.
# - Use `supabase.table("<table_name>").select("id", count="exact")` as the base query.
# - Apply filters dynamically based on the user input:
#   - **Partial text matches:** Use `.ilike("<column_name>", "%<value>%")` (e.g., `branch`).
#   - **Exact matches:** Use `.eq("<column_name>", <value>)` for specific values like `date`.
#   - **Date range filtering:**
#     - If `from_date` is provided, use `.gte("date", "<from_date>")`.
#     - If `to_date` is provided, use `.lte("date", "<to_date>")`.
# - Ensure the output is a **single valid Python statement** that can be executed directly with `.execute()`.
# """,
#                     },
#                     {
#                         "role": "user",
#                         "content": f"Count the number of records in the database based on: {input}",
#                     },
#                 ],
#             )
#             .choices[0]
#             .message.content
#         )
#         log_message(f"```{query_code}```")
#
#         if "select(" not in query_code:
#             return {"error": "Only SELECT queries are allowed"}
#
#         log_message("Fetching data...")
#         exec(query_code, globals())
#         response = query.execute()
#
#         if response and hasattr(response, "data"):
#             log_message(f"Query successful, retrieved {len(response.data)} records.")
#             print(response.count)
#             return {"results": response.count}
#         else:
#             log_message("  Query returned an unexpected response.")
#             return {"error": "Unexpected response format"}
#
#     except Exception as e:
#         log_message(f"Error occurred: {e}")
#         return {"error": str(e)}


def call_tool(tool_call):
    try:
        log_message("Detecting the arguments...")
        args = json.loads(tool_call.function.arguments)
        log_message(f"```{args}```")
        tool_name = tool_call.function.name

        if tool_name == "get_pdf_related_data":
            return get_pdf_related_data(args)
        elif tool_name == "get_pdf_by_content":
            return get_pdf_by_content(args)
        elif tool_name == "summarize_pdf":
            return summarize_pdf(args)
        elif tool_name == "query_pdf":
            return query_pdf(args)

        return {"error": "Unknown tool"}
    except json.JSONDecodeError:
        return {"error": "Invalid arguments format"}


def run_agent(user_id, session_id, user_message):
    now = datetime.now()
    result = supabase.table("documents").select("id", count="exact").execute()
    total_records = result.count if result.count is not None else "N/A"
    print(now.strftime("%H:%M:%S %d-%m-%Y"))

    system_prompt = f"""
        You are an AI assistant for querying and summarizing financial department documents. When you receive data from a tool call (presented as a 'tool' message in the conversation), please use that information to provide a complete answer. If the tool returns a list of documents, list them in your answer. If the query is ambiguous, ask clarifying questions.
        <context>
            Total records in the database: {total_records}
            Current time: {now.strftime("%H:%M:%S %m-%d-%Y")} 
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
                "name": "get_pdf_by_content",
                "description": "Given the content, retrieve the pdf from the vector store using similarity search",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "content": {
                            "type": "string",
                            "description": "Get the content from the user query that they wants to search in the pdf",
                        }
                    },
                    "required": ["query"],
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
        # {
        #     "type": "function",
        #     "function": {
        #         "name": "count_records",
        #         "description": "Based on the input, count the number of records in the database",
        #         "parameters": {
        #             "type": "object",
        #             "properties": {
        #                 "date": {
        #                     "type": "string",
        #                     "description": "Date/Year e.g. 12/06/2005, 2023, Jan 2019. For a range, use 'from_date' and 'to_date' instead.",
        #                 },
        #                 "from_date": {
        #                     "type": "string",
        #                     "description": "Start date e.g. 2023-01-01",
        #                 },
        #                 "to_date": {
        #                     "type": "string",
        #                     "description": "End date e.g. 2023-12-31",
        #                 },
        #                 "branch": {
        #                     "type": "string",
        #                     "enum": [
        #                         "A-(Public Sector Undertaking)",
        #                         "CH-(Service Matter)",
        #                         "K-(Budget)",
        #                         "M-(Pay of Government Employee)",
        #                         "PayCell-(Pay Commission)",
        #                         "N-(Banking)",
        #                         "P-(Pension)",
        #                         "T-(Local Establishment)",
        #                         "TH-(Value Added Tax)",
        #                         "TH-3-(Commercial Tax Establishment)",
        #                         "Z-(Treasury)",
        #                         "Z-1-(Economy)",
        #                         "G-(Audit Para)",
        #                         "GH-(Accounts Cadre Establishment)",
        #                         "FR-(Financial Resources)",
        #                         "DMO-(Debt Management)",
        #                         "GO Cell-(Government Companies)",
        #                         "B-RTI Cell-(Small Savings RTI)",
        #                         "KH",
        #                         "PMU-Cell",
        #                         "GST Cell",
        #                     ],
        #                     "description": "Branch name",
        #                 },
        #             },
        #         },
        #     },
        # },
        {
            "type": "function",
            "function": {
                "name": "query_pdf",
                "description": "Process the pdf and answer the user query based on the content of the pdf",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pdf_url": {"type": "string", "description": "PDF URL"},
                        "query": {"type": "string", "description": "User query"},
                    },
                    "required": ["pdf_url", "query"],
                },
            },
        },
    ]

    while True:
        messages = get_chat_history(user_id, session_id)
        messages.insert(0, {"role": "system", "content": system_prompt})
        response = call_agent(messages, tools)

        assistant_msg = response.model_dump()
        store_message(user_id, session_id, assistant_msg)

        if response.content:
            st.session_state.log_history = []
            logs_placeholder.empty()
            logs_placeholder.markdown("- No logs yet")
            st.chat_message("assistant").write(response.content)
            return

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


if __name__ == "__main__":
    user_id = "user_13"
    session_id = "session_456"

    st.title("FinBot")

    with st.sidebar.expander("**Processing Logs**", expanded=True):
        logs_placeholder = st.empty()
        if st.session_state.log_history:
            logs_placeholder.markdown(
                "".join(f"- {msg}" for msg in st.session_state.log_history)
            )
        else:
            logs_placeholder.markdown("- No logs yet")

    for msg in get_chat_history(user_id, session_id):
        if msg["role"] == "system" or msg["role"] == "tool" or not msg.get("content"):
            continue
        role = "user" if msg["role"] == "user" else "assistant"
        content = msg.get("content", "")
        if content:
            st.chat_message(role).write(content)

    user_input = st.chat_input("Type your query here...")
    if user_input:
        user_msg = {"role": "user", "content": user_input}
        st.chat_message("user").write(user_input)
        store_message(user_id, session_id, user_msg)
        with st.spinner("Processing..."):
            run_agent(user_id, session_id, user_msg)
