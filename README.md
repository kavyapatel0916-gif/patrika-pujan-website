# Patrika Pujan – Editable Guest Name Website

This website uses the original five-page Patrika Pujan PDF as its source. **Only the guest name is added to the existing blank guest-name lines on pages 1 and 5.** Nothing else in the invitation is replaced or rewritten.

## Run locally

1. Install Python 3.10+ (PyMuPDF is the only external Python dependency).
2. Open a terminal in this folder.
3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Start the website:

```bash
python app.py
```

5. Open `http://127.0.0.1:5000` in your browser.
6. Enter the guest name, click **Preview**, then click **Download PDF**.

The downloaded PDF keeps the original 5-page invitation and adds the entered guest name in Gujarati-compatible font.
