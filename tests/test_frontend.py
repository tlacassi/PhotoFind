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
        const setInterval = () => 1; const window = {addEventListener(){}};
        const document = {addEventListener(){}, createTextNode(text){return text}, querySelector(selector){return elements[selector] || null}, querySelectorAll(){return []}, createElement:node};
        class FormData { append(key,value){this.file=value;} }
        let fakeJobs = [];
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
          const id = 'job-' + index;
          xhr.status = error ? 400 : 202;
          xhr.responseText=JSON.stringify(error ? {detail:error} : {id,name:xhr.file.name,status:'queued'});
          if (!error) fakeJobs.push({id,name:xhr.file.name,status:'queued'}); xhr.onload();
        }
        const fetch = async (url, options={}) => {
          calls.push({url,...options});
          if (url==='/api/me') return {ok:true,json:async()=>viewer};
          if (url.startsWith('/api/photo-jobs')) return {ok:true,json:async()=>({jobs:fakeJobs,remaining:fakeJobs.filter(job=>job.status==='queued').length})};
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
        for name in ('app.js','admin.js','invite.js','viewer.js'):
            quickjs.Context().eval('(function(){\n' + (ROOT / 'static' / name).read_text() + '\n})')

    def test_concurrent_upload_progress_retry_and_stop(self):
        context = self.context()
        source = (ROOT / 'static' / 'app.js').read_text().replace('if (photoInput) {', 'if (false) {')
        context.eval(source)
        context.eval("selectedGallery={...gallery}; me=viewer; var finished=false; uploadBatch([{name:'one',size:10},{name:'bad',size:10},{name:'three',size:10},{name:'four',size:10},{name:'five',size:10}]).then(()=>{finished=true});")
        self.assertEqual(context.eval('requests.length'), 3)
        context.eval('transfer(0);transfer(1);transfer(2);')
        self.assertIn('3 enregistrement', context.eval("elements['#upload-status'].textContent"))
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
        self.assertNotIn('id="auto-cover"', (ROOT / 'static' / 'index.html').read_text())

    def test_viewer_navigation_for_clients_and_photographers(self):
        context = quickjs.Context()
        context.eval("""
        const items = {};
        for (const id of ['#viewer-image','#viewer-position','#viewer-previous','#viewer-next','#viewer-download','#viewer-close']) items[id]={listeners:{},addEventListener(type,callback){this.listeners[type]=callback},removeAttribute(name){delete this[name]}};
        const dialog={open:false,listeners:{},querySelector(id){return items[id]},addEventListener(type,callback){this.listeners[type]=callback},showModal(){this.open=true},close(){this.open=false;this.listeners.close()}};
        const document={querySelector(){return dialog}};
        """)
        context.eval((ROOT / 'static' / 'viewer.js').read_text())
        context.eval("openPhotoViewer([{id:'a',name:'one.jpg'},{id:'b',name:'two.jpg'}],0,{client:true,galleryId:'g'});")
        self.assertTrue(context.eval('dialog.open'))
        self.assertTrue(context.eval("items['#viewer-previous'].disabled"))
        context.eval("dialog.listeners.keydown({key:'ArrowRight',preventDefault(){}});")
        self.assertEqual(context.eval("items['#viewer-position'].textContent"),'2 / 2')
        self.assertIn('/api/client/photos/b/image',context.eval("items['#viewer-image'].src"))
        self.assertTrue(context.eval("items['#viewer-next'].disabled"))
        context.eval("items['#viewer-close'].listeners.click();")
        self.assertFalse(context.eval('dialog.open'))
        context.eval("openPhotoViewer([{id:'a',name:'one.jpg'}],0,{client:false});")
        self.assertEqual(context.eval("items['#viewer-image'].src"),'/api/photos/a/image')
