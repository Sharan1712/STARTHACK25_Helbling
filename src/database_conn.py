import pymysql
from pyannote.audio import Model, Inference
from qdrant_client import QdrantClient
import uuid
import random

class ConversationDB:
    
    def __init__(self):
        self.db_conn = pymysql.connect(host="database-2.c14g8ugigyfj.eu-central-1.rds.amazonaws.com",
                                       user = "admin",
                                       password="Spkgw123#",
                                       database="users_db")
        self.user_table = "user_data"
        self.color = '\033[94m'
        self.reset = '\033[0m'
        
        
    def get_user_data(self):
        db_cursor = self.db_conn.cursor()
        db_cursor.execute(f"Select * from {self.user_table}")
        data = db_cursor.fetchall()
        
        return data
    
    def add_new_user(self, data):
        db_cursor = self.db_conn.cursor()
        insert_query = f"Insert into {self.user_table} (user_id, memory_summary) values ('{str(data.get("user_id"))}', '{str(data.get("memory"))}')"
        # print(insert_query)
        print(f"{self.color} Adding New User ({data.get("user_id")}) to Memory DataBase{self.reset}")
        db_cursor.execute(insert_query)
        self.db_conn.commit()
        db_cursor.close()
    
    def update_existing_user(self, data):
        db_cursor = self.db_conn.cursor()
        update_query = f"Update {self.user_table} set memory_summary = '{str(data.get("memory"))}' where user_id='{data.get('user_id')}'"
        print(print(f"{self.color} Updating User ({data.get("user_id")}) in Memory DataBase{self.reset}"))
        db_cursor.execute(update_query)
        self.db_conn.commit()
        db_cursor.close()
        
class AudioVectorDB:
    
    def __init__(self):
        qdrant_uri = 'https://e381cc1c-54d2-40fb-a903-d0df59ccf19b.europe-west3-0.gcp.cloud.qdrant.io' # Paste your URI
        qdrant_api_key = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhY2Nlc3MiOiJtIn0.bODd65Rq0v41q_HxoQbBQYTagtOD3gE6y38FOGly6pQ' # Paste your API KEY
        self.qdrant_client = QdrantClient(url = qdrant_uri, api_key=qdrant_api_key)
        
        speech_emb_model = Model.from_pretrained("pyannote/embedding", use_auth_token="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")
        self.inference = Inference(speech_emb_model, window="whole")
        self.color = '\033[92m'
        self.reset = '\033[0m'
        
    def add_new_user_emb(self, users, emb):
        # emb = self.inference(file)
        print(f"{self.color}USER VOICE DETECTOR: Adding New User{self.reset}")
        users += 1
        embedding_dict = [{"id":str(uuid.uuid4()), "payload":{"user_id":f"USER{users}"},"vector": emb.tolist()}]
        self.qdrant_client.upsert('my_collection', points=embedding_dict)
        with open("src/constants.txt", "w") as f:
            f.write(str(users))
        return f"USER{users}"
        
    def check_existing_user(self, users, file = "audio.wav"):
        emb = self.inference(file)
        results = self.qdrant_client.search("my_collection", emb,  with_vectors=False, with_payload=True)
        print(results[0].score)
        if results[0].score >= 0.40:
            print(f"{self.color}USER VOICE DETECTOR: I recognize this customer{self.reset}")
            return results[0].payload.get('user_id')
        else:
            print(f"{self.color}USER VOICE DETECTOR: I do not recognize this customer{self.reset}")
            return self.add_new_user_emb(users, emb) 


        