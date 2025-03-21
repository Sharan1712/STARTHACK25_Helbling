from df.enhance import enhance, init_df, load_audio, save_audio
import time
import boto3
import datetime
import warnings
warnings.simplefilter("ignore")
warnings.filterwarnings("ignore", category=DeprecationWarning)
# import logging
# log = logging.getLogger('werkzeug')
# logging.getLogger("DF").setLevel(logging.INFO)
# logging.getLogger("DF").setLevel(logging.ERROR)
# logging.getLogger("DF").setLevel(logging.WARNING)

AWS_ACCESS_KEY_ID = 'AKIA3VF7BMBFXC2OEMHI'  
AWS_SECRET_ACCESS_KEY = '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' 
AWS_REGION = 'eu-central-1'

def check_file_presence(timeout_seconds, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION):
    obj = boto3.client("s3",
                    aws_access_key_id=AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                    region_name=AWS_REGION)  
    
    model, df_state, _ = init_df()
    start_time = time.time()
    while time.time() - start_time < timeout_seconds:  
             
        found_files = []
        response = obj.list_objects_v2(Bucket = "starthackbucket", Prefix="audio")
   
        if 'Contents' in response:
                for fileobj in response['Contents']:                
                    found_files.append(fileobj['Key'])
    
    
        if len(found_files) > 0:
            found_files.sort(key=lambda x: x.split("audio")[1].split(".wav")[0])

            obj.download_file(
                "starthackbucket",
                found_files[0],
                found_files[0]
            )
            print("Downloaded:",found_files[0])
            obj.delete_object(
                        Bucket = "starthackbucket",
                        Key = found_files[0]
                    )
            print("Deleted:",found_files[0])
           
            audio, _ = load_audio(found_files[0], sr=df_state.sr())
            enhanced = enhance(model, df_state, audio)
            
            now = datetime.datetime.now()
            timestamp = now.strftime("%Y%m%d%H%M%S%f") 
            file_name = "denoisedaudio_"+ timestamp +".wav"
            save_audio(file_name, enhanced, df_state.sr())
            obj.upload_file(
                    Filename=file_name,
                    Bucket="denoisedbucket",
                    Key= file_name
                )    
            print("Uploaded:",file_name)
            print("-----")

check_file_presence(300, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION)

