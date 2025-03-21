import streamlit as st
from datetime import datetime
import os
import boto3
import warnings
from transcriptor import transcribe_audio  # Import the transcribe_audio function from transcriptor.py

warnings.simplefilter("ignore")
warnings.filterwarnings("ignore", category=DeprecationWarning)

AWS_ACCESS_KEY_ID = 'AKIA3VF7BMBFXC2OEMHI'  # Replace with your actual key
AWS_SECRET_ACCESS_KEY = 'sx9ZYqOrda40AKRuif60TAt624YR6LFKFVlHdvfY' # Replace with your actual secret key
AWS_REGION = 'eu-central-1'

def upload_file(audio_file_name, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION):
    s3_obj = boto3.client("s3",
                    aws_access_key_id=AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                    region_name=AWS_REGION)
    
    s3_obj.upload_file(
        Filename=audio_file_name,
        Bucket="starthackbucket",
        Key=os.path.basename(audio_file_name)
    )

    return f"s3://starthackbucket/{os.path.basename(audio_file_name)}"

# 📂 Set your designated folder path here
SAVE_PATH = "recordings"
os.makedirs(SAVE_PATH, exist_ok=True)

st.set_page_config(page_title="Audio Recorder and Transcription", layout="centered")
st.title("🎤 Streamlit Audio Recorder and Transcription")

st.write("Click **Start Recording** to begin. Then click **Stop Recording** to save the audio.")

# Use session state to manage recording toggle
if 'recording' not in st.session_state:
    st.session_state.recording = False
if 'audio_data' not in st.session_state:
    st.session_state.audio_data = None
if 'transcription' not in st.session_state:
    st.session_state.transcription = ""

# Start Recording button
if not st.session_state.recording:
    if st.button("🎙️ Start Recording"):
        st.session_state.recording = True

# If recording started, show the recorder widget
if st.session_state.recording:
    audio_data = st.audio_input("🎤 Recording... Speak now")
    st.session_state.audio_data = audio_data

    # Stop Recording button
    if st.button("Save recording"):
        st.session_state.recording = False
        audio_data = st.session_state.audio_data

        if audio_data is not None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"recording_{timestamp}.wav"
            filepath = os.path.join(SAVE_PATH, filename)

            with open(filepath, "wb") as f:
                f.write(audio_data.getvalue())

            st.success(f"✅ Audio saved as `{filename}` in `{SAVE_PATH}`")
            
            # Upload the file to S3
            s3_url = upload_file(filepath, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION)

            # Transcribe the audio
            transcription_result = transcribe_audio(filepath)
            if "error" in transcription_result:
                st.error(transcription_result["error"])
            else:
                st.session_state.transcription = transcription_result["text"]
            st.audio(audio_data)  # Optional playback
        else:
            st.warning("⚠️ No audio was recorded.")

# Display transcription
if st.session_state.transcription:
    st.write("### Transcription")
    st.write(st.session_state.transcription)