import warnings
warnings.filterwarnings('ignore')
from dotenv import load_dotenv
load_dotenv()

import logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

import uuid
import json
import os
import random

from flask import Flask, request, jsonify
from flask_sock import Sock
from flask_cors import CORS
from flasgger import Swagger

from database_conn import ConversationDB
from database_conn import AudioVectorDB
from aws_conn import upload_audio_file, down_audio_file

from openai import OpenAI
import pandas as pd
import io

AZURE_SPEECH_KEY = os.getenv("AZURE_SPEECH_KEY")
AZURE_SPEECH_REGION = os.getenv("AZURE_SPEECH_REGION")
OPENAI_KEY = os.getenv("OPENAI_KEY")
client = OpenAI(api_key=OPENAI_KEY)

qdrant_uri = os.getenv("qdrant_uri")
qdrant_api_key = os.getenv("qdrant_api_key")


app = Flask(__name__)
sock = Sock(app)
cors = CORS(app)
swagger = Swagger(app)

memory_database = ConversationDB()
audio_database = AudioVectorDB(qdrant_uri, qdrant_api_key)

with open("src/constants.txt", "r") as f:
  users = int(f.read())

blue = '\033[94m'
green = '\033[92m'
reset = '\033[0m'

sessions = {}
chats = {}

def save_audio(audio_file):
    with open(audio_file.name, "wb") as f:
      f.write(audio_file.getvalue())

def add_message_to_history(chat_session_id, role, msg):  
  if chats[chat_session_id]["conversation_history"] is not None:
    chats[chat_session_id]["conversation_history"].append({"role":role,"content":msg.get('text')})
  else:
    chats[chat_session_id]["conversation_history"] = [{"role":role,"content":msg.get('text')}]

def transcribe_whisper(audio_recording, denoise = False):
    audio_file = io.BytesIO(audio_recording)
    audio_file.name = 'audio.wav'  # Whisper requires a filename with a valid extension
    save_audio(audio_file)
    
    if denoise:
      upload_audio_file(os.getenv("AWS_ACCESS_KEY_ID"), os.getenv("AWS_SECRET_ACCESS_KEY"), os.getenv("AWS_REGION"))
      audio_file = down_audio_file(os.getenv("AWS_ACCESS_KEY_ID"), os.getenv("AWS_SECRET_ACCESS_KEY"), os.getenv("AWS_REGION"))
      audio_file = f"{audio_file}.wav"
    
    transcription = client.audio.transcriptions.create(
        model="whisper-1",
        file=audio_file,
        # language =   # specify Language explicitly
    )
    print(f"{green}USER MESSAGE: {transcription.text}{reset}")
    return transcription.text
    
def transcribe_preview(session):
    if session["audio_buffer"] is not None:
        text = transcribe_whisper(session["audio_buffer"])
        # send transcription
        ws = session.get("websocket")
        if ws:
            message = {
                "event": "recognizing",
                "text": text,
                "language": session["language"]
            }
            ws.send(json.dumps(message))
        return text

@app.route("/chats/<chat_session_id>/sessions", methods=["POST"])
def open_session(chat_session_id):
    """
    Open a new voice input session and start continuous recognition.
    ---
    tags:
      - Sessions
    parameters:
      - name: chat_session_id
        in: path
        type: string
        required: true
        description: ID of the chat session
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - language
          properties:
            language:
              type: string
              description: Language code for speech recognition (e.g., en-US)
    responses:
      200:
        description: Session created successfully
        schema:
          type: object
          properties:
            session_id:
              type: string
              description: Unique identifier for the voice recognition session
      400:
        description: Language parameter missing
        schema:
          type: object
          properties:
            error:
              type: string
              description: Description of the error
    """
    session_id = str(uuid.uuid4())
    print("-----------------------------------------------------SESSION START-----------------------------------------------------")

    body = request.get_json()
    if "language" not in body:
        return jsonify({"error": "Language not specified"}), 400
    language = body["language"]
    
    sessions[session_id] = {
        "audio_buffer": None,
        "chatSessionId": chat_session_id,
        "language": language,
        "text": None,
        "user_status": None,
        "user_id": None,
        "conversation_history": None,
        "memories": None,
        "websocket": None,  # will be set when the client connects via WS
    }
    
    if not chats.get(chat_session_id): 
      chats[chat_session_id] = {
        "chatSessionId": chat_session_id,
        "language": language,
        "user_status": None,
        "user_id": None,
        "conversation_history": None,
        "memories": None,
        "count": 1,
      }

    return jsonify({"session_id": session_id})


@app.route("/chats/<chat_session_id>/sessions/<session_id>/wav", methods=["POST"])
def upload_audio_chunk(chat_session_id, session_id):
    """
    Upload an audio chunk (expected 16kb, ~0.5s of WAV data).
    The chunk is appended to the push stream for the session.
    ---
    tags:
      - Sessions
    parameters:
      - name: chat_session_id
        in: path
        type: string
        required: true
        description: ID of the chat session
      - name: session_id
        in: path
        type: string
        required: true
        description: ID of the voice input session
      - name: audio_chunk
        in: body
        required: true
        schema:
          type: string
          format: binary
          description: Raw WAV audio data
    responses:
      200:
        description: Audio chunk received successfully
        schema:
          type: object
          properties:
            status:
              type: string
              description: Status message
      404:
        description: Session not found
        schema:
          type: object
          properties:
            error:
              type: string
              description: Description of the error
    """
    # print("UPLOAD AUDIO")
    if session_id not in sessions:
        return jsonify({"error": "Session not found"}), 404

    audio_data = request.get_data()  # raw binary data from the POST body
    
    if sessions[session_id]["audio_buffer"] is not None:
      sessions[session_id]["audio_buffer"] = sessions[session_id]["audio_buffer"] + audio_data
    else:
      sessions[session_id]["audio_buffer"] = audio_data
      
    # TODO optionally transcribe real time audio chunks, see transcribe_preview()
    
    if sessions[session_id]["audio_buffer"] is not None:
      text = transcribe_preview(sessions[session_id])
    
    return jsonify({"status": "audio_chunk_received"})


@app.route("/chats/<chat_session_id>/sessions/<session_id>", methods=["DELETE"])
def close_session(chat_session_id, session_id):
    """
    Close the session (stop recognition, close push stream, cleanup).
    
    ---
    tags:
      - Sessions
    parameters:
      - name: chat_session_id
        in: path
        type: string
        required: true
        description: The ID of the chat session
      - name: session_id
        in: path
        type: string
        required: true
        description: The ID of the session to close
    responses:
      200:
        description: Session successfully closed
        schema:
          type: object
          properties:
            status:
              type: string
              example: session_closed
      404:
        description: Session not found
        schema:
          type: object
          properties:
            error:
              type: string
              example: Session not found
    """
    print("-----------------------------------------------------CLOSING SESSION-----------------------------------------------------")
    if session_id not in sessions:
        return jsonify({"error": "Session not found"}), 404


    if sessions[session_id]["audio_buffer"] is not None:
        # TODO preprocess audio/text, extract and save speaker identification
        sessions[session_id]["text"] = transcribe_whisper(sessions[session_id]["audio_buffer"], denoise = False)
        
        if sessions[session_id]["user_status"] is None:
          sessions[session_id]["user_id"] = audio_database.check_existing_user(users)
          chats[chat_session_id]["user_id"] = sessions[session_id]["user_id"]
        
        existing_customers = pd.read_sql("Select * from user_data", memory_database.db_conn)
        # print(existing_customers)
        if sessions[session_id]["user_id"] in existing_customers["user_id"].unique().tolist():
          
          print(f"{blue}We know this customers preferences{reset}")
          
          sessions[session_id]["user_status"] = "Old Customer"
          chats[chat_session_id]["user_status"] = "Old Customer"
          
          memory = existing_customers[existing_customers["user_id"] == chats[chat_session_id]["user_id"]]["memory_summary"].values[0]
          sessions[session_id]["memories"] = memory
          chats[chat_session_id]["memories"] = memory
        
        else:
          print(f"{blue}No history with {chats[chat_session_id]["user_id"]}{reset}")
          sessions[session_id]["user_status"] = "New Customer"
          chats[chat_session_id]["user_status"] = "New Customer"
          # with open("src/constants.txt", "r") as f:
          #   users = int(f.read())
 
        # send transcription
        ws = sessions[session_id].get("websocket")
        if ws:
          user_status = chats[chat_session_id]["user_status"]
          count = chats[chat_session_id]["count"]
          
          weather = random.choice(['warm', 'cold', 'chilly', 'hot', 'rainy', 'dry'])
          holiday = random.choice(['Haloween', 'NA', 'NA', 'NA', 'Easter', 'NA', 'NA', 'NA', 'Christmas', 'New Year', 'NA', 'OktoberFest', 'NA', 'NA'])
          add_on_prompt = f"""\nThis above was the query by a {user_status} (user status). If {count}>1, just focus on the question
          Act as a very professional waiter, in addition to answering the query:
          1. Greet the user according to the user status.
          2. You can also suggest specials of the day, be creative and to the point with this. (Ignore if {count}>1)
          3. or Drinks based on todays {weather} (Ignore if {count}>1)
          4. or Come up with holiday/occasion specials. Current Holiday: {holiday} (Ignore if {count}>1)
          These are not compulsory. Do this very rarely please. And do not do all of them. If there is a holiday, prioritize this and wish the customer as well.
          Keep it short. Do not repeat stuff."""
          message = {
              "event": "recognized",
              "text": sessions[session_id]["text"] + add_on_prompt,
              "language": sessions[session_id]["language"]
          }
          ws.send(json.dumps(message))
          chats[chat_session_id]["count"] += 1
    
    # # Remove from session store
    sessions.pop(session_id, None)

    return jsonify({"status": "session_closed"})


@sock.route("/ws/chats/<chat_session_id>/sessions/<session_id>")
def speech_socket(ws, chat_session_id, session_id):
    """
    WebSocket endpoint for clients to receive STT results.

    This WebSocket allows clients to connect and receive speech-to-text (STT) results
    in real time. The connection is maintained until the client disconnects. If the 
    session ID is invalid, an error message is sent, and the connection is closed.

    ---
    tags:
      - Sessions
    parameters:
      - name: chat_session_id
        in: path
        type: string
        required: true
        description: The unique identifier for the chat session.
      - name: session_id
        in: path
        type: string
        required: true
        description: The unique identifier for the speech session.
    responses:
      400:
        description: Session not found.
      101:
        description: WebSocket connection established.
    """
    if session_id not in sessions:
        ws.send(json.dumps({"error": "Session not found"}))
        
    print("SPEECH SOCKET")
    # Store the websocket reference in the session
    sessions[session_id]["websocket"] = ws

    # Keep the socket open to send events
    # Typically we'd read messages from the client in a loop if needed
    while True:
        # If the client closes the socket, an exception is thrown or `ws.receive()` returns None
        msg = ws.receive()
        if msg is None:
            break

@app.route('/chats/<chat_session_id>/set-memories', methods=['POST'])
def set_memories(chat_session_id):
    """
    Set memories for a specific chat session.

    ---
    tags:
      - Memories
    parameters:
      - name: chat_session_id
        in: path
        type: string
        required: true
        description: The unique identifier of the chat session.
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            chat_history:
              type: array
              items:
                type: object
                properties:
                  text:
                    type: string
                    description: The chat message text.
              description: List of chat messages in the session.
    responses:
      200:
        description: Memory set successfully.
        schema:
          type: object
          properties:
            success:
              type: string
              example: "1"
      400:
        description: Invalid request data.
    """
    print("-----------------------------------------------------ENTERING SET MEMORIES-----------------------------------------------------")
    chat_history = request.get_json()
    
    
    # if not isinstance(chats[chat_session_id]["conversation_history"], list):
    #   return jsonify({"error": "Chat history is of invalid format"}), 400
        
    # TODO preprocess data (chat history & system message) Here we can use what shivam had sent on the group to identify user behaviours
    for msg in chat_history[-3:]:
      if msg.get("audioFilePath") is not None:
        pass
        # print("Audio dict skipped")
      elif msg.get("type") == 0:
        add_message_to_history(chat_session_id, role = "user", msg = msg)
      else:
        add_message_to_history(chat_session_id, role = "assistant", msg = msg)
    
    print(f"{green}{chats[chat_session_id]["conversation_history"][-1]}{reset}")
    # print(f"{chat_session_id} extracting memories for conversation a:{chat_history[-1]['text']}")

    return jsonify({"success": "1"})


@app.route('/chats/<chat_session_id>/get-memories', methods=['GET'])
def get_memories(chat_session_id):
    """
    Retrieve stored memories for a specific chat session.
    ---
    tags:
      - Memories
    parameters:
      - name: chat_session_id
        in: path
        type: string
        required: true
        description: The unique identifier of the chat session.
    responses:
      200:
        description: Successfully retrieved memories for the chat session.
        schema:
          type: object
          properties:
            memories:
              type: string
              description: The stored memories for the chat session.
      400:
        description: Invalid chat session ID.
      404:
        description: Chat session not found.
    """
    print("-----------------------------------------------------GET MEMORIES-----------------------------------------------------")
    # print(f"{chat_session_id}: updating memories...")
    # print(chats[chat_session_id]["conversation_history"])
    # print(chats[chat_session_id]["user_status"])
    
      
    if chats[chat_session_id]["user_status"] == "Old Customer":
      summary_messages = {"role":"system", 
                          "content": f"""You are a helpful assistant for a restaurant. You're task is to update your observations about existing customers. 
                          You have a look at the conversations of your AI Powered waiter with a customer along with the customers old summary and generate a summary of what the customer likes and dislikes and what are the favorite orders.
                          Strictly fix to observing likes, dislikes, prefrences, allergies etc. DO NOT INCLUDE ANY OTHER INFORMATION.
                          Here is the old summary of the customer: {chats[chat_session_id]["memories"]}
                            
                          Make sure the output looks like this:
                          Preferred Food: If a user has ordered a food multiple times based on memories and chat history or Not sure but xyz if you are somewhat uncertain and NA if you are clueless
                          Likes: food or cuisine the user likes to order or NA if not sure
                          Dislikes: food or cuisine the user doesn't like or NA if not sure
                          Allergies: if the user mentions an allergy or NA if not sure
                          Dietary Restrictions: if any
                          Type: Vegan or Vegetarian or Non Vegertarian or NA if not sure
                          Do not use any single or double apostrophe in your answer"""}
    else:
      summary_messages = {"role":"system", 
                            "content": f"""You are a helpful assistant for a restaurant. You're task is to generate your observations about New customers. 
                            You have a look at the conversations of your AI Powered waiter with a customer and generate a summary of what the customer likes and dislikes and what are the favorite orders.
                            Strictly fix to observing likes, dislikes, prefrences, allergies etc. DO NOT INCLUDE ANY OTHER INFORMATION.
                            
                            Make sure the output looks like this:
                            Likes: food the user likes to order or NA if not sure
                            Dislikes: food the user doesn't want or NA if not sure
                            Allergies: if the user mentions an allergy or NA if not sure
                            Type: Vegan or Vegetarian or Non Vegertarian or NA if not sure
                            Dietary Restrictions: if any
                            If you are unsure of any, just say New customer: could not grasp much information
                            Do not use any single or double apostrophe in your answer"""}
      
    if chats[chat_session_id]["conversation_history"] is not None:
      conversation_history = "\n".join(str(msg) for msg in chats[chat_session_id]["conversation_history"])
      messages = [summary_messages, {"role": "user", "content": conversation_history}]
    else:
      messages = [summary_messages]
      
    completion = client.chat.completions.create(
      model = "gpt-4o-mini",
      messages = messages
      )
      
    summary = completion.choices[0].message.content
       
    print(f"{blue}User Summary: {summary}{reset}")
    
    if chats[chat_session_id]["user_status"] == "New Customer":
      data = {"user_id":chats[chat_session_id]["user_id"], "memory":summary}
      memory_database.add_new_user(data)
    else:
      data = {"user_id":chats[chat_session_id]["user_id"], "memory":summary}
      memory_database.update_existing_user(data)

    # TODO load relevant memories from your database. Example return value:
    if chats[chat_session_id]["user_status"] == "Old Customer":
      summary = chats[chat_session_id]["memories"]
    else:
      summary = "New customer: could not grasp much information"
      
    return jsonify({"memories": summary})


if __name__ == "__main__":
    # In production, you would use a real WSGI server like gunicorn/uwsgi
    app.run(debug=True, host="0.0.0.0", port=5000)
    