from flask import Flask, request, jsonify
import os
from datetime import datetime

app = Flask(__name__)

@app.route('/save_audio', methods=['POST'])
def save_audio():
    if 'audio' not in request.files:
        return jsonify({"error": "No audio file detected"}), 400

    audio = request.files['audio']
    
    # Create a directory for storing audio files if it doesn't exist
    if not os.path.exists('uploads'):
        os.makedirs('uploads')

    # Generate a timestamp for the audio file name
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    filename = f"recording_{timestamp}.wav"
    filepath = os.path.join('uploads', filename)

    # Save the file
    audio.save(filepath)

    return jsonify({"message": "Audio saved successfully", "filename": filename}), 200

if __name__ == "__main__":
    app.run(debug=True, port=5000)