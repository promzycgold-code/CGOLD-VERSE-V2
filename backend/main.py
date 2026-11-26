import time
from backend.jobs import job_manager, JobCancelled
import os, subprocess, tempfile, threading, logging, math
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response
from functools import lru_cache
import base64

app = FastAPI(title='CGOLD VERSE V2')
lock = threading.Lock()
LIMIT = 100 * 1024 * 1024
ROOT = Path(__file__).resolve().parents[1]

def run(args, job_id=None):
    with tempfile.TemporaryFile() as errors, subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=errors) as proc:
        deadline = time.monotonic() + 1800
        try:
            while proc.poll() is None:
                if job_id: job_manager.check_cancelled(job_id)
                if time.monotonic() > deadline: raise subprocess.TimeoutExpired(args, 1800)
                time.sleep(.2)
            if proc.returncode: raise subprocess.CalledProcessError(proc.returncode, args)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()


def validate(start, end, speed, model):
    if not all(map(math.isfinite, (start,end,speed))) or start < 0 or end <= start or end-start > 600 or speed not in (1,.85,.7) or model not in ('tiny','base','small','medium'):
        raise ValueError('Invalid selection, speed or model; maximum selection is 10 minutes.')

@lru_cache(maxsize=1)
def get_model(name):
    from faster_whisper import WhisperModel
    return WhisperModel(name, device='cpu', compute_type='int8')

def transcribe(path, model, language, start, speed, job_id=None, low=55, high=95, duration=1):
    segments, info = get_model(model).transcribe(str(path), language=language or None, beam_size=5, vad_filter=False, word_timestamps=True)
    rows = []
    for seg in segments:
        if job_id:
            job_manager.update(job_id, 'Transcribing audio', min(high, low + int((high-low)*seg.end*speed/max(duration, .1))))
        rows.append({'start':round(start+seg.start*speed,2), 'end':round(start+seg.end*speed,2), 'text':seg.text.strip(), 'words':[{'text':w.word,'start':round(start+w.start*speed,2),'end':round(start+w.end*speed,2),'confidence':w.probability} for w in (seg.words or [])]})
    return {'text':'\n'.join(r['text'] for r in rows), 'segments':rows, 'language':info.language}

@app.get('/api/health')
def health():
    return {'status':'ok'}

@app.post('/api/transcribe')
def process(audio: UploadFile=File(...), start:float=Form(0), end:float=Form(...), speed:float=Form(.85), model:str=Form('base'), language:str=Form(''), isolate:bool=Form(True), compare:bool=Form(False), normalize:bool=Form(True), noise:bool=Form(False)):
    check_options(start,end,speed,model,language)
    if not lock.acquire(blocking=False): raise HTTPException(429,'Another audio job is running. Try again later.')
    try:
        return pipeline(audio.file,start,end,speed,model,language,isolate,compare,normalize,noise)
    finally:
        audio.file.close(); lock.release()

def check_options(start,end,speed,model,language):
    try: validate(start,end,speed,model)
    except ValueError as e: raise HTTPException(400,str(e))
    if language not in ('','en','fr','es','pt','de','ar','zh','ja','ko','hi','it','ru','tr','nl','id','sw'): raise HTTPException(400,'Unsupported language')

def pipeline(source,start,end,speed,model,language,isolate,compare,normalize,noise,job_id=None):
    def stage(label, percent):
        if job_id: job_manager.update(job_id,label,percent)
    def execute(args): run(args,job_id)
    try:
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder); src=p/'upload'; selected=p/'selected.wav'; processed=p/'processed.wav'
            stage("Preparing audio", 5)
            size=0
            with src.open('wb') as out:
                while chunk:=source.read(1024*1024):
                    size+=len(chunk)
                    if size>LIMIT: raise HTTPException(413,'Maximum upload is 100 MB')
                    out.write(chunk)
            execute(['ffmpeg','-nostdin','-v','error','-y','-ss',str(start),'-i',str(src),'-t',str(end-start),'-vn','-ac','2','-ar','44100',str(selected)])
            vocal=selected
            preview=None
            if isolate:
                stage("Isolating vocals (Demucs)", 15)
                import sys
                execute([sys.executable,'-m','demucs','-n','htdemucs','--two-stems=vocals','-d','cpu','-o',str(p/'stems'),str(selected)])
                vocal=p/'stems'/'htdemucs'/'selected'/'vocals.wav'
                preview=p/'vocals.mp3'
                execute(['ffmpeg','-nostdin','-v','error','-y','-i',str(vocal),'-b:a','128k',str(preview)])
            stage("Enhancing audio", 45)
            filters=[]
            if noise: filters.append('afftdn')
            if normalize: filters.append('loudnorm=I=-20:TP=-2:LRA=11')
            filters.append(f'atempo={speed}')
            execute(['ffmpeg','-nostdin','-v','error','-y','-i',str(vocal),'-af',','.join(filters),'-ac','1','-ar','16000',str(processed)])
            stage("Loading model / transcribing", 55)
            result=transcribe(processed,model,language,start,speed,job_id,55,75 if compare else 95,end-start)
            if compare:
                stage('Comparing original audio',75)
                result['original']=transcribe(selected,model,language,start,1,job_id,75,95,end-start)
            stage('Preparing results', 98)
            if preview: result['vocals']='data:audio/mpeg;base64,'+base64.b64encode(preview.read_bytes()).decode()
            return result
    except (HTTPException, JobCancelled): raise
    except subprocess.TimeoutExpired: raise HTTPException(504,'Audio processing timed out. Select a shorter section.')
    except Exception:
        logging.exception('Audio processing failed')
        raise HTTPException(422,'Processing failed. Check audio format, FFmpeg, model download and available memory. See server terminal.')

@app.post('/api/jobs', status_code=202)
def start_job(audio: UploadFile=File(...), start:float=Form(0), end:float=Form(...), speed:float=Form(.85), model:str=Form('base'), language:str=Form(''), isolate:bool=Form(True), compare:bool=Form(False), normalize:bool=Form(True), noise:bool=Form(False)):
    check_options(start,end,speed,model,language)
    if not lock.acquire(blocking=False): raise HTTPException(429,'Another audio job is running. Try again later.')
    source = None
    try:
        source = tempfile.TemporaryFile()
        size = 0
        while chunk := audio.file.read(1024*1024):
            size += len(chunk)
            if size > LIMIT: raise HTTPException(413,'Maximum upload is 100 MB')
            source.write(chunk)
        source.seek(0)
        job_id = job_manager.create()
        def worker():
            try:
                result = pipeline(source,start,end,speed,model,language,isolate,compare,normalize,noise,job_id)
                job_manager.complete(job_id,result)
            except JobCancelled: job_manager.mark_cancelled(job_id)
            except HTTPException as exc: job_manager.fail(job_id,exc.detail)
            except Exception:
                logging.exception('Job failed')
                job_manager.fail(job_id,'Processing failed')
            finally:
                source.close()
                lock.release()
        threading.Thread(target=worker,daemon=True).start()
        return {'id':job_id}
    except Exception:
        if source: source.close()
        lock.release()
        raise
    finally: audio.file.close()

@app.get("/api/jobs/{job_id}")
def get_job_status(job_id: str):
    job = job_manager.get(job_id)

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Job not found"
        )

    return job


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    job = job_manager.get(job_id)

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Job not found"
        )

    if not job_manager.cancel(job_id):
        raise HTTPException(
            status_code=409,
            detail="Job cannot be cancelled"
        )

    return {
        "status": "cancelling",
        "id": job_id
    }
app.mount('/',StaticFiles(directory=ROOT/'static',html=True),name='frontend')
