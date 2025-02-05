import os
from dotenv import load_dotenv
from deep_translator import GoogleTranslator
from bs4 import BeautifulSoup
from supabase import create_client
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

load_dotenv()

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
supabase = create_client(url, key)


def click_dropdown_menu(driver):
    dropdown_menu = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.CLASS_NAME, "jqTransformSelectWrapper"))
    )
    dropdown_menu.click()


def get_ul_element(driver):
    return WebDriverWait(driver, 10).until(
        EC.presence_of_element_located(
            (By.XPATH, "//div[@class='jqTransformSelectWrapper']//ul")
        )
    )


def scrape(base_url):
    print("Scraping...")

    chrome_web_driver_path = "./chromedriver"
    options = webdriver.ChromeOptions()

    download_dir = os.path.abspath("pdfs")
    os.makedirs(download_dir, exist_ok=True)

    prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "plugins.always_open_pdf_externally": True,
    }
    options.add_experimental_option("prefs", prefs)
    options.add_argument("--headless=new")

    driver = webdriver.Chrome(service=Service(chrome_web_driver_path), options=options)

    try:
        driver.get(base_url)
        print("Page loaded successfully")

        click_dropdown_menu(driver)

        ul_element = get_ul_element(driver)
        li_elements = ul_element.find_elements(By.TAG_NAME, "li")

        for i in range(3, len(li_elements) - 2):
            if i != 0:
                click_dropdown_menu(driver)  # Open dropdown again
                WebDriverWait(driver, 5).until(EC.visibility_of(get_ul_element(driver)))
                li_elements = get_ul_element(driver).find_elements(By.TAG_NAME, "li")

            branch = li_elements[i].get_attribute("innerText")

            driver.execute_script("arguments[0].scrollIntoView();", li_elements[i])
            WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable(li_elements[i])
            ).click()

            print(f"Extracting data for {branch}...")

            table = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "table"))
            )
            soup = BeautifulSoup(table.get_attribute("outerHTML"), "html.parser")

            extracted_data = []
            print(f"{len(soup.find_all('tr'))} records are there in {branch}")
            for row in soup.find_all("tr"):
                cols = row.find_all("td")
                if len(cols) == 4:
                    gr_no = cols[0].text.strip()
                    date = cols[1].text.strip()
                    subject = cols[2].text.strip()
                    pdf_link = cols[3].find("a")["href"] if cols[3].find("a") else None

                    subject_en = GoogleTranslator(source="auto", target="en").translate(
                        subject
                    )
                    subject_gu = GoogleTranslator(source="auto", target="gu").translate(
                        subject
                    )

                    pdf_url = (
                        f"https://financedepartment.gujarat.gov.in/{pdf_link}"
                        if pdf_link
                        else None
                    )
                    extracted_data.append(
                        {
                            "gr_no": gr_no,
                            "date": date,
                            "branch": branch,
                            "subject_en": subject_en,
                            "subject_gu": subject_gu,
                            "pdf_url": pdf_url,
                        }
                    )
                    print(
                        f"Extracted data for {gr_no} currently at {len(extracted_data)}"
                    )
                    if len(extracted_data) == 25:
                        supabase.table("documents").insert(extracted_data).execute()
                        print(f"Inserted {len(extracted_data)} records for {branch}")
                        print("Resetting extracted_data")
                        extracted_data = []

            if extracted_data:
                supabase.table("documents").insert(extracted_data).execute()
                print(f"Inserted {len(extracted_data)} records for {branch}")

    except Exception as e:
        print(f"Error: {e}")

    finally:
        driver.quit()
        print("Driver closed")


if __name__ == "__main__":
    scrape("https://financedepartment.gujarat.gov.in/gr.html")
