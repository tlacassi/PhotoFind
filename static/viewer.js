const photoViewer = document.querySelector('#photo-viewer');
let viewerPhotos = [], viewerIndex = 0, viewerScope = null;
function viewerPhotoURL(photo) {
  return viewerScope?.client ? `/api/client/photos/${photo.id}/image?gallery_id=${encodeURIComponent(viewerScope.galleryId)}` : `/api/photos/${photo.id}/image`;
}
function updatePhotoViewer() {
  const photo = viewerPhotos[viewerIndex];
  photoViewer.querySelector('#viewer-image').src = viewerPhotoURL(photo);
  photoViewer.querySelector('#viewer-image').alt = `Photo ${viewerIndex + 1} sur ${viewerPhotos.length}`;
  photoViewer.querySelector('#viewer-position').textContent = `${viewerIndex + 1} / ${viewerPhotos.length}`;
  photoViewer.querySelector('#viewer-previous').disabled = viewerIndex === 0;
  photoViewer.querySelector('#viewer-next').disabled = viewerIndex === viewerPhotos.length - 1;
  const download = photoViewer.querySelector('#viewer-download'); download.href = viewerPhotoURL(photo);
  download.download = photo.name.replace(/\.[^.]+$/, '') + '.jpg';
}
function openPhotoViewer(photos, index, scope) {
  if (!photos.length || index < 0 || index >= photos.length) return;
  viewerPhotos = photos; viewerIndex = index; viewerScope = scope; updatePhotoViewer();
  if (!photoViewer.open) photoViewer.showModal();
}
function stepPhotoViewer(step) {
  const next = viewerIndex + step;
  if (next >= 0 && next < viewerPhotos.length) { viewerIndex = next; updatePhotoViewer(); }
}
if (photoViewer) {
  photoViewer.querySelector('#viewer-close').addEventListener('click', () => photoViewer.close());
  photoViewer.querySelector('#viewer-previous').addEventListener('click', () => stepPhotoViewer(-1));
  photoViewer.querySelector('#viewer-next').addEventListener('click', () => stepPhotoViewer(1));
  photoViewer.addEventListener('keydown', event => {
    if (event.key === 'ArrowRight') { event.preventDefault(); stepPhotoViewer(1); }
    if (event.key === 'ArrowLeft') { event.preventDefault(); stepPhotoViewer(-1); }
  });
  photoViewer.addEventListener('close', () => { photoViewer.querySelector('#viewer-image').removeAttribute('src'); viewerPhotos = []; });
}
