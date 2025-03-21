import logging
from transformers import pipeline

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load the Speech-to-Text model (Whisper)
logger.info("Loading Whisper model for speech recognition...")
stt_pipeline = pipeline("automatic-speech-recognition", model="openai/whisper-base")
logger.info("Whisper model loaded successfully.")

def transcribe_audio(file_path):
    """ Convert audio to text using the Whisper model """
    logger.info(f"🎤 Processing audio file: {file_path}")
    try:
        result = stt_pipeline(file_path)
        transcribed_text = result.get('text', None)
        logger.info(f"📝 Transcribed Text: {transcribed_text}")
        if not transcribed_text:
            logger.error("Transcription failed.")
            return {"error": "Transcription failed."}
        
        return {"text": transcribed_text}
    except Exception as e:
        logger.error(f"Error processing audio: {e}")
        return {"error": f"Failed to process audio: {e}"}

# For testing purposes, can be removed in production
if __name__ == "__main__":
    test_audio = "sample_audio.wav"  # Replace with your actual audio file path
    output = transcribe_audio(test_audio)
    if output and not output.get("error"):
        print("Recognized Speech:", output["text"])
    else:
        print(f"Processing failed: {output.get('error', 'Unknown error')}")