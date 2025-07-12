
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

def send_email(transcript, call_sid):
    sender_email = "neatliner@gmail.com"
    receiver_email = "seda.soyletir@brightstar-sales.com"
    password = os.getenv("GMAIL_APP_PASSWORD")

    subject = f"Neatliner Customer Call Summary (CallSid: {call_sid})"
    body = "Here is the conversation transcript:\n\n" + transcript

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
