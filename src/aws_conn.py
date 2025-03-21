import boto3
import datetime
import time

def upload_audio_file(AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION):
    
    obj = boto3.client("s3",
                    aws_access_key_id=AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                    region_name=AWS_REGION)
    
    now = datetime.datetime.now()
    timestamp = now.strftime("%Y%m%d%H%M%S%f") 
    obj.upload_file(Filename="audio.wav", Bucket="starthackbucket", Key="audio"+ timestamp +".wav")
    # time.sleep(1)
    print(timestamp)
    
def down_audio_file(AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION):
    
    found_files = []
    obj = boto3.client("s3", aws_access_key_id=AWS_ACCESS_KEY_ID, aws_secret_access_key=AWS_SECRET_ACCESS_KEY, region_name=AWS_REGION)
    response = obj.list_objects_v2(Bucket = "denoisedbucket", Prefix="denoised")
    
    if 'Contents' in response:
        for fileobj in response['Contents']:
            found_files.append(fileobj['Key'])

    if len(found_files) > 0:
        found_files.sort(key=lambda x: x.split("audio")[1].split(".wav")[0])
        obj.download_file("denoisedbucket", found_files[0], found_files[0])
    
        print("Downloaded:",found_files[0])
        # obj.delete_object(Bucket = "denoisedbucket", Key = found_files[0])
        # print("Deleted:",found_files[0])
        # obj.download_file("denoisedbucket", file_path, download_path)
        return found_files[0]
    else:
        return "NA"


