/** @odoo-module **/

// 1. สร้าง CSS รอไว้ก่อน (ยังไม่สร้าง Element)
const style = document.createElement('style');
style.innerHTML = `
    .custom-zoom-overlay {
        position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
        background: rgba(0,0,0,0.9); z-index: 99999;
        display: none; justify-content: center; align-items: center;
        cursor: zoom-out;
    }
    .custom-zoom-overlay.active {
        display: flex !important; animation: fadeIn 0.2s;
    }
    .custom-zoom-overlay img {
        max-width: 90%; max-height: 90%; 
        object-fit: contain;
        box-shadow: 0 0 20px rgba(255,255,255,0.1);
    }
    .custom-loading-spinner {
        color: white; font-size: 20px; position: absolute;
    }
    .o_field_image img { cursor: zoom-in !important; }
    @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
`;
document.head.appendChild(style);

let overlay = null;
let overlayImg = null;
let spinner = null;

// 2. ฟังก์ชันสร้าง Overlay (เรียกใช้เมื่อคลิกครั้งแรกเท่านั้น)
function createOverlay() {
    if (overlay) return; // ถ้ามีแล้ว ไม่ต้องสร้างใหม่

    overlay = document.createElement('div');
    overlay.className = 'custom-zoom-overlay';
    overlay.innerHTML = '<div class="custom-loading-spinner">Loading...</div><img src="" style="display:none;" />';
    document.body.appendChild(overlay);

    overlayImg = overlay.querySelector('img');
    spinner = overlay.querySelector('.custom-loading-spinner');

    // คลิกเพื่อปิด
    overlay.onclick = () => { 
        overlay.classList.remove('active');
        // เคลียร์ src เพื่อประหยัด Memory
        setTimeout(() => { overlayImg.src = ''; }, 200);
    };
}

// 3. ฟังก์ชันแปลง URL
function getFullSizeUrl(src) {
    if (!src) return src;
    if (src.includes('/web/image')) {
        return src.replace(/\/image_\d+/, '/image_1920')
                  .replace(/field=image_\d+/, 'field=image_1920'); 
    }
    return src;
}

// 4. Global Event Listener
document.addEventListener('click', (e) => {
    // เช็คว่าคลิกรูปใน Odoo Image Field
    if (e.target.tagName === 'IMG' && e.target.closest('.o_field_image')) {
        let src = e.target.src;
        if (src && !src.includes('/placeholder') && !src.includes('assets/common')) {
            e.preventDefault();
            e.stopPropagation();

            // สร้าง Overlay ถ้ายังไม่มี
            createOverlay();

            // Reset สถานะ
            overlay.classList.add('active');
            spinner.style.display = 'block';
            overlayImg.style.display = 'none';

            // เริ่มโหลดรูป
            const fullSrc = getFullSizeUrl(src);
            overlayImg.src = fullSrc;

            overlayImg.onload = () => {
                spinner.style.display = 'none';
                overlayImg.style.display = 'block';
            };

            overlayImg.onerror = () => {
                // ถ้าโหลดรูปใหญ่ไม่ได้ ให้ใช้รูปเดิม
                overlayImg.src = src;
                spinner.style.display = 'none';
                overlayImg.style.display = 'block';
            };
        }
    }
}, true);
