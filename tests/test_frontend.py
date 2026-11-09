"""Execute frontend flows with a minimal DOM and transport fake, not a browser."""
import json
import re
import unittest
from pathlib import Path
import quickjs

ROOT = Path(__file__).resolve().parents[1]


class FrontendTests(unittest.TestCase):
    def context(self):
        context = quickjs.Context()
        context.eval('''
        const elements = {};
        function node() { return {hidden:false, disabled:false, value:0, children:[], listeners:{}, append(...items){this.children.push(...items)}, replaceChildren(...items){this.children=items}, addEventListener(type,fn){this.listeners[type]=fn}, setAttribute(){}, showModal(){this.open=true}, close(){this.open=false}}; }
        const document = {querySelector(selector){return elements[selector] || null}, querySelectorAll(){return []}, createElement:node};
        class FormData { append(key,value){this.file=value;} }
        let requests = [], calls = [], gallery = {id:'gallery', name:'Original', archived:0, owner_id:1, photo_count:0, cover_photo_id:'manual'}, viewer = {id:1,role:'admin',used_bytes:0,quota_bytes:null};
        const location = {origin:'http://localhost',assign(){}};
        const prompt = () => 'Renamed'; const confirm = () => true;
        class XMLHttpRequest {
          constructor(){this.upload={};}
          open(method,url){this.url=url;}
          send(data){this.file=data.file;requests.push(this);}
        }
        function transfer(index) {
          const xhr=requests[index]; xhr.upload.onprogress({lengthComputable:true,loaded:5,total:10});
          xhr.upload.onprogress({lengthComputable:true,loaded:10,total:10}); xhr.upload.onload();
        }
        function complete(index,error) {
          const xhr=requests[index];xhr.status=200;
          xhr.responseText=JSON.stringify([{name:xhr.file.name,...(error ? {error} : {faces:1})}]);xhr.onload();
        }
        const fetch = async (url, options={}) => {
          calls.push({url,...options});
          if (url==='/api/me') return {ok:true,json:async()=>viewer};
          if (url==='/api/galleries') return {ok:true,json:async()=>[{...gallery}]};
          if (options.method==='PATCH' && url==='/api/galleries/gallery') Object.assign(gallery,JSON.parse(options.body));
          return {ok:true,json:async()=>[]};
        };
        ''')
        for element_id in re.findall(r'id="([^"]+)"', (ROOT / 'static/index.html').read_text()):
            context.eval(f'elements[{json.dumps("#" + element_id)}]=node();')
        return context

    def drain(self, context):
        for _ in range(1000):
            if not context.execute_pending_job(): return
        self.fail('JavaScript promises did not settle')

    def test_scripts_parse(self):
        for name in ('app.js','admin.js','invite.js'):
            quickjs.Context().eval('(function(){\n' + (ROOT / 'static' / name).read_text() + '\n})')

    def test_concurrent_upload_progress_retry_and_stop(self):
        context = self.context()
        source = (ROOT / 'static' / 'app.js').read_text().replace('if (photoInput) {', 'if (false) {')
        context.eval(source)
        context.eval("selectedGallery={...gallery}; me=viewer; var finished=false; uploadBatch([{name:'one',size:10},{name:'bad',size:10},{name:'three',size:10},{name:'four',size:10},{name:'five',size:10}]).then(()=>{finished=true});")
        self.assertEqual(context.eval('requests.length'), 3)
        context.eval('transfer(0);transfer(1);transfer(2);')
        self.assertIn('3 analyse', context.eval("elements['#upload-status'].textContent"))
        self.assertEqual(context.eval("elements['#upload-progress'].value"), 60)
        context.eval('complete(0);'); self.drain(context)
        self.assertEqual(context.eval('requests.length'), 4)
        self.assertFalse(context.eval('finished'))
        context.eval("stopUpload=true;transfer(3);complete(1,'invalid');complete(2);complete(3);")
        self.drain(context)
        self.assertTrue(context.eval('finished'))
        self.assertEqual(json.loads(context.eval('JSON.stringify(failedUploads.map(file=>file.name))')), ['bad','five'])
        self.assertFalse(context.eval("elements['#retry-upload'].hidden"))
        context.eval('uploadBatch([...failedUploads]);')
        self.assertEqual(context.eval('requests.length'), 6)
        context.eval('transfer(4);transfer(5);complete(4);complete(5);'); self.drain(context)
        self.assertEqual(context.eval('failedUploads.length'), 0)
        self.assertFalse(context.eval('photoInput.disabled'))
        self.assertTrue(context.eval("elements['#retry-upload'].hidden"))

    def test_gallery_action_handlers_and_feedback(self):
        context = self.context(); context.eval((ROOT / 'static' / 'app.js').read_text()); self.drain(context)
        context.eval("loadGalleries('gallery');"); self.drain(context)
        context.eval("elements['#rename-gallery'].listeners.click();"); self.drain(context)
        self.assertEqual(context.eval('selectedGallery.name'), 'Renamed')
        context.eval("elements['#archive-gallery'].listeners.click();"); self.drain(context)
        self.assertTrue(context.eval('Boolean(selectedGallery.archived)'))
        self.assertEqual(context.eval("elements['#archive-gallery'].textContent"), 'Activer la galerie')
        self.assertTrue(context.eval('photoInput.disabled'))
        context.eval("elements['#archive-gallery'].listeners.click();"); self.drain(context)
        self.assertFalse(context.eval('Boolean(selectedGallery.archived)'))
        context.eval("elements['#auto-cover'].listeners.click();"); self.drain(context)
        self.assertIsNone(context.eval('selectedGallery.cover_photo_id'))
        self.assertIn('Miniature automatique activée', context.eval("elements['#gallery-status'].textContent"))
        context.eval("uploading=true; const before=calls.length; elements['#auto-cover'].listeners.click();")
        self.drain(context)
        self.assertEqual(context.eval('calls.length'), context.eval('before'))
