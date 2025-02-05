import os

url = "https://financedepartment.gujarat.gov.in/Documents/CH_275_10-Jun-1971_564.pdf"
output_path = "CH_275_10-Jun-1971_564.pdf"

os.system(f'aria2c -x 16 -s 16 -o "{output_path}" "{url}"')


def get_pdf_related_data(input):
    print("inside get_pdf_related_data")
    try:
        query = supabase.table("documents").select("*")

        if "gr_no" in input and input["gr_no"]:
            query = query.eq("gr_no", input["gr_no"])
        if "date" in input and input["date"]:
            query = query.eq("date", {input["date"]})
        if "branch" in input and input["branch"]:
            query = query.eq("branch", input["branch"])
        if "subject" in input and input["subject"]:
            query = query.ilike("subject", f"%{input['subject']}%")
        if "content" in input and input["content"]:
            query = query.ilike("content", f"%{input['content']}%")

        response = query.execute()
        print(response)

        return {"results": response.data}
    except Exception as e:
        return {"error": str(e)}
