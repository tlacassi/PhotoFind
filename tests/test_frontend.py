"""Execute frontend flows with a minimal DOM and transport fake, not a browser."""
import json
import unittest
from pathlib import Path
import quickjs

ROOT = Path(__file__).resolve().parents[1]


class FrontendTests(unittest.TestCase):
    def test_scripts_parse(self):
        for name in ('app.js','admin.js'):
            quickjs.Context().eval('(function(){\n' + (ROOT / 'static' / name).read_text() + '\n})')

    def test_upload_progress_failures_retry_and_stop(self):
        context = quickjs.Context()
        context.eval('''
        const elements = {};
        function node() { return {hidden:false, disabled:false, value:0, children:[], append(...items){this.children.push(...items)}, replaceChildren(...items){this.children=items}, addEventListener(){}, setAttribute(){}}; }
        const document = {querySelector(selector){return elements[selector] || null}, createElement:node};
        ['#photos','#selfie','#open-create-gallery','#gallery-list','#clear','#rename-gallery','#archive-gallery','#cancel-upload','#retry-upload','#upload-progress','#upload-details','#upload-status','#count','#library'].forEach(key=>elements[key]=node());
        // Avoid running startup branches while defining the functions under test.
        delete elements['#photos']; delete elements['#selfie'];
        class FormData { append(key,value){this.file=value;} }
        let sent = [], failOnce = true, stopAfterFirst = false, progressSeen = false;
        class XMLHttpRequest {
          constructor(){this.upload={};}
          open(method,url){this.url=url;}
          send(data){
            sent.push(data.file.name);
            this.upload.onprogress({lengthComputable:true,loaded:5,total:10});
            progressSeen = elements['#upload-status'].textContent.includes('50 %');
            this.upload.onload();
            this.status=200;
            this.responseText=JSON.stringify([{name:data.file.name,...(data.file.name==='bad' && failOnce ? {error:'invalid'} : {faces:1})}]);
            if (data.file.name==='bad') failOnce=false;
            if(stopAfterFirst) stopUpload=true;
            this.onload();
          }
        }
        const fetch = async () => ({ok:true,json:async()=>[]});
        ''')
        source = (ROOT / 'static' / 'app.js').read_text().replace("const photoInput = $('#photos'), selfieInput = $('#selfie');", "const photoInput = node(), selfieInput = null;").replace('if (photoInput) {', 'if (false) {')
        context.eval(source)
        context.eval("elements['#photos']=photoInput; selectedGallery={id:'gallery',archived:false}; me={role:'admin'}; var finished=false; uploadBatch([{name:'good'},{name:'bad'}]).then(()=>{finished=true});")
        for _ in range(100):
            if not context.execute_pending_job(): break
        self.assertTrue(context.eval('finished'))
        self.assertTrue(context.eval('progressSeen'))
        self.assertEqual(context.eval('failedUploads.length'), 1)
        self.assertFalse(context.eval("elements['#retry-upload'].hidden"))
        context.eval('uploadBatch([...failedUploads]);')
        while context.execute_pending_job(): pass
        self.assertEqual(json.loads(context.eval('JSON.stringify(sent)')), ['good','bad','bad'])
        self.assertEqual(context.eval('failedUploads.length'), 0)
        context.eval("sent=[]; stopAfterFirst=true; uploadBatch([{name:'one'},{name:'two'}]);")
        while context.execute_pending_job(): pass
        self.assertEqual(json.loads(context.eval('JSON.stringify(sent)')), ['one'])
        self.assertEqual(context.eval('failedUploads[0].name'), 'two')
        self.assertFalse(context.eval('photoInput.disabled'))
