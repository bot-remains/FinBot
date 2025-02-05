from dotenv import load_dotenv

load_dotenv()

import os
from supabase import create_client
from openai import OpenAI
import httpx
from pdf2image import convert_from_bytes
import pytesseract
from langchain_text_splitters import RecursiveCharacterTextSplitter

openai = OpenAI()
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
supabase = create_client(url, key)

urls = [
    "https://financedepartment.gujarat.gov.in/Documents/A_2424_01-Jul-2010_737.pdf",
    "https://financedepartment.gujarat.gov.in/Documents/A_2851_26-Sep-2024_956.pdf",
    "https://financedepartment.gujarat.gov.in/Documents/CH_2558_02-May-2022_993.PDF",
    "https://financedepartment.gujarat.gov.in/Documents/CH_143_28-May-2004_874.pdf",
    "https://financedepartment.gujarat.gov.in/Documents/CH_1820_01-Jan-2007_858.pdf",
    "https://financedepartment.gujarat.gov.in/Documents/CH_61_07-Feb-2011_121.PDF",
    "https://financedepartment.gujarat.gov.in/Documents/M_411_03-Oct-2000_9.pdf",
    "https://financedepartment.gujarat.gov.in/Documents/K_2858_23-Jan-2025_134.pdf",
    "https://financedepartment.gujarat.gov.in/Documents/T_2822_24-May-2024_347.pdf",
    "https://financedepartment.gujarat.gov.in/Documents/CH_2821_04-Jul-2024_596.PDF",
    "https://financedepartment.gujarat.gov.in/Documents/P_2575_29-Jul-2022_248.pdf",
    "https://financedepartment.gujarat.gov.in/Documents/A_2376_11-Jun-2020_786.pdf",
    "https://financedepartment.gujarat.gov.in/Documents/DMO_2394_19-Oct-2020_439.pdf",
    "https://financedepartment.gujarat.gov.in/Documents/P_2214_26-Dec-2018_705.PDF",
    "https://financedepartment.gujarat.gov.in/Documents/Z_2220_13-Feb-2019_629.PDF",
    "https://financedepartment.gujarat.gov.in/Documents/P_2222_27-Feb-2019_876.PDF",
]

for url in urls:
    print(f"Processing {url}")
    with httpx.Client() as client:
        response = client.get(url)
        response.raise_for_status()

    pdf_binary = response.content
    images = convert_from_bytes(pdf_binary)

    print("Extracting text...")
    text = ""
    for img in images:
        page_text = pytesseract.image_to_string(img, lang="eng+guj")
        text += page_text + "\n"

    print("Splitting text...")
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
        length_function=len,
        is_separator_regex=False,
        separators=["\n\n", "\n", "."],
    )
    chunks = text_splitter.split_text(text)
    print(f"Extracted {len(chunks)} chunks")

    query = supabase.table("documents").select("*").eq("pdf_url", url).execute()
    print(query)

    doc_id = query.data[0]["id"]
    print(f"Document ID: {doc_id}")

    for chunk_number, chunk in enumerate(chunks, start=1):
        embedding_response = openai.embeddings.create(
            model="text-embedding-3-small", input=chunk
        )
        embedding = embedding_response.data[0].embedding

        data = {
            "doc_id": doc_id,
            "chunk_no": chunk_number,
            "body": chunk,
            "embedding": embedding,
        }

        supabase.table("vectors").insert(data).execute()

    print(f"Processed and inserted {len(chunks)} chunks for {url}")
