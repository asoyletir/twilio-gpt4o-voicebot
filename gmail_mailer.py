import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

def send_email(transcript, call_sid, metadata):
    sender_email = "neatliner@gmail.com"
    receiver_email = "seda.soyletir@brightstar-sales.com"
    password = os.getenv("GMAIL_APP_PASSWORD")

    subject = f"Neatliner Customer Call Summary (CallSid: {call_sid})"

    body = f"""Neatliner Customer Service – Call Summary

📌 Call Type: {metadata.get("call_type", "Not Identified")}
📞 Caller Number: {metadata.get("from_number", "Unknown")}
🌍 Location: {metadata.get("location", "Unknown")}
📧 Email Address: {metadata.get("email", "Not Provided")}
🛒 Order Number: {metadata.get("order_number", "Not Provided")}

🎙 Conversation Transcript:
{transcript}
"""

    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = receiver_email
    msg["Subject"] = subject

    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, password)
            server.sendmail(sender_email, receiver_email, msg.as_string())
        print("Email sent successfully.")
    except Exception as e:
        print(f"Error sending email: {e}")
