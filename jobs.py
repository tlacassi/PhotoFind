"""Persistent local processing queue; requests only transfer files to disk."""
import threading

import storage


class ProcessingQueue:
    def __init__(self, database, process, cleanup, thumbnail, workers=2):
        self.database = database
        self.process = process
        self.cleanup = cleanup
        self.thumbnail = thumbnail
        self.workers = workers
        self.stop_event = threading.Event()
        self.threads = []

    def start(self):
        with storage.connect(self.database) as db:
            db.execute("UPDATE photo_jobs SET status='queued' WHERE status='processing'")
        for index in range(self.workers):
            thread = threading.Thread(target=self.run, name=f'photo-worker-{index}', daemon=True)
            thread.start(); self.threads.append(thread)
        thread = threading.Thread(target=self.run_thumbnails, name='photo-thumbnails', daemon=True)
        thread.start(); self.threads.append(thread)

    def stop(self):
        self.stop_event.set()
        for thread in self.threads:
            thread.join()

    def claim(self):
        with storage.connect(self.database) as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT * FROM photo_jobs WHERE status='queued' ORDER BY rowid LIMIT 1").fetchone()
            if row:
                db.execute("UPDATE photo_jobs SET status='processing' WHERE id=?", (row['id'],))
                return dict(row)

    def run(self):
        import logging
        while not self.stop_event.is_set():
            job = self.claim()
            if not job:
                self.stop_event.wait(.3); continue
            try:
                result = self.process(job)
                with storage.connect(self.database) as db:
                    db.execute('UPDATE photos SET thumbnail_status=0 WHERE thumbnail_status=2 AND gallery_id=?',(job['gallery_id'],))
                    db.execute("UPDATE photo_jobs SET status='done', faces=?, photo_id=?, input_bytes=0 WHERE id=?", (result['faces'],result['photo_id'],job['id']))
            except Exception as error:
                from fastapi import HTTPException
                detail = str(error.detail) if isinstance(error, HTTPException) else str(error)
                if not isinstance(error, (HTTPException, ValueError, RuntimeError)):
                    logging.exception('Background processing failed for job %s', job['id'])
                    detail = 'Traitement impossible. Consultez les journaux serveur.'
                with storage.connect(self.database) as db:
                    db.execute("UPDATE photo_jobs SET status='error', error=?, input_bytes=0 WHERE id=?", (detail,job['id']))
            finally:
                try:
                    self.cleanup(job)
                except OSError:
                    logging.exception('Could not clean incoming job %s',job['id'])

    def run_thumbnails(self):
        import logging
        while not self.stop_event.is_set():
            try:
                if not self.thumbnail(): self.stop_event.wait(1)
            except Exception:
                logging.exception('Thumbnail generation failed')
                self.stop_event.wait(3)
