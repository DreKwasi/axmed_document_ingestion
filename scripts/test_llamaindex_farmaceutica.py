"""Test reading Farmaceutica PDF using LlamaIndex PDF reader and extracting the table."""

from pathlib import Path
import re
from llama_index.readers.file import PDFReader

def main():
    pdf_path = Path("backend/evals/fixtures/documents/farmaceutica_andina_proforma_FA-COT-2026-118.pdf")
    if not pdf_path.exists():
        print(f"Error: File not found at {pdf_path}")
        return

    print(f"Reading document with LlamaIndex: {pdf_path.name}\n")
    reader = PDFReader()
    documents = reader.load_data(file=pdf_path)

    print(f"Loaded {len(documents)} page(s) via LlamaIndex.\n")

    # Extract the table portion from Page 1
    page1_text = documents[0].text
    if "1.  Schedule of prices" in page1_text:
        table_section = page1_text.split("1.  Schedule of prices")[1].split("Subtotal, FOB Cartagena")[0]
        print("=" * 70)
        print("LLAMAINDEX EXTRACTED TABLE SECTION:")
        print("=" * 70)
        print(table_section.strip())
        print("\n" + "=" * 70)
        print("FORMATTED TABLE ROWS EXTRACTED FROM LLAMAINDEX OUTPUT:")
        print("=" * 70)
        
        # Parse into structured rows based on item numbers 01-06
        lines = [l.strip() for l in table_section.splitlines() if l.strip()]
        # Skip header lines until "01"
        start_idx = 0
        for i, l in enumerate(lines):
            if l == "01":
                start_idx = i
                break

        # Group lines by item numbers
        item_indices = []
        for i in range(start_idx, len(lines)):
            if re.match(r"^0[1-9]$", lines[i]):
                item_indices.append(i)
        item_indices.append(len(lines))

        headers = ["Item", "Product", "INN", "Presentation", "UOM", "Quantity", "Unit Price ($)", "Disc (%)", "Extended ($)"]
        print(f"| {' | '.join(headers)} |")
        print(f"|{':---:|' + ':---|' * 3 + ':---:|' + '---:|' * 4}")

        for k in range(len(item_indices) - 1):
            chunk = lines[item_indices[k]:item_indices[k+1]]
            item_num = chunk[0]
            prod_name = chunk[1]
            inn = chunk[2]
            # The last 5 tokens of each item chunk are UOM, Qty, Price, Disc, Extended
            uom = chunk[-5]
            qty = chunk[-4]
            price = chunk[-3]
            disc = chunk[-2]
            extended = chunk[-1]
            # Everything between INN and UOM is the Presentation
            presentation = " ".join(chunk[3:-5])
            
            row = [item_num, prod_name, inn, presentation, uom, qty, price, disc, extended]
            print(f"| {' | '.join(row)} |")
        print("=" * 70 + "\n")

    # Optional: If LLAMA_CLOUD_API_KEY is available, also test LlamaParse cloud parser
    import os
    llama_key = os.environ.get("LLAMA_CLOUD_API_KEY")
    if llama_key:
        try:
            from llama_parse import LlamaParse
            print("Found LLAMA_CLOUD_API_KEY. Testing LlamaParse cloud parser:")
            parser = LlamaParse(api_key=llama_key, result_type="markdown")
            lp_docs = parser.load_data(str(pdf_path))
            print(lp_docs[0].text[:1000])
        except Exception as e:
            print(f"LlamaParse error: {e}")



if __name__ == "__main__":
    main()
