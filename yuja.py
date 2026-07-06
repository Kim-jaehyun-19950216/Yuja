import streamlit as st
import os
import requests
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from bs4 import BeautifulSoup
from PIL import Image as PILImage
from io import BytesIO

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Flowable, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT, TA_LEFT
from reportlab.lib.utils import ImageReader
from google.oauth2.service_account import Credentials

def get_creds():
    # Streamlit Cloud의 .streamlit/secrets.toml에 저장된 내용을 가져옴
    return Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive.readonly']
    )
# Streamlit 페이지 설정
st.set_page_config(page_title="구글 시트 -> PDF 변환기", layout="wide")

FONT_REGULAR = "malgun.ttf"
FONT_BOLD = "malgunbd.ttf"

# ==========================================
# PDF 렌더링 클래스 및 크롤링 함수 (기존 로직 동일)
# ==========================================
class AbsoluteBottomRightImages(Flowable):
    def __init__(self, images_data, max_h):
        Flowable.__init__(self)
        self.images_data = images_data
        self.max_h = max_h 

    def wrap(self, availWidth, availHeight):
        return 0, 0

    def draw(self):
        c = self.canv
        page_w, page_h = c._pagesize
        
        abs_x, abs_y = c.absolutePosition(0, 0)
        c.saveState()
        c.translate(-abs_x, -abs_y)
        
        base_h = 201.0
        target_h = min(base_h, max(10.0, self.max_h - 20))
        
        avail_w_for_imgs = page_w 
        max_w_per_img = avail_w_for_imgs / max(1, len(self.images_data))
        
        total_w = 0
        processed_images = []
        for img_io in self.images_data:
            try:
                pil_img = PILImage.open(img_io)
                ow, oh = pil_img.size
                aspect = ow / float(oh)
                h = target_h
                w = h * aspect
                
                if w > max_w_per_img:
                    w = max_w_per_img
                    h = w / aspect
                    
                processed_images.append((ImageReader(img_io), w, h))
                total_w += w
            except Exception:
                pass
                
        current_x = page_w - total_w
        current_y = 0
        for img_reader, w, h in processed_images:
            c.drawImage(img_reader, current_x, current_y, width=w, height=h)
            current_x += w
            
        c.restoreState()

def get_image_from_url(url):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200: return None
            
        soup = BeautifulSoup(response.text, 'html.parser')
        img_url = None
        
        slides = soup.select('.swiper-slide img')
        for img in slides:
            src = img.get('src')
            if src and 'thumbnail' in src:
                img_url = src
                break
                
        if not img_url:
            for img in soup.find_all('img'):
                src = img.get('src')
                if src and 'thumbnail' in src and 'webdesign' in src:
                    img_url = src
                    break
                    
        if not img_url and 'branduid=' in url:
            try:
                branduid = url.split('branduid=')[1].split('&')[0]
                for img in soup.find_all('img'):
                    src = img.get('src')
                    if src and branduid in src:
                        img_url = src
                        break
            except:
                pass
                
        if not img_url: return None
            
        if img_url.startswith('//'): img_url = 'https:' + img_url
        elif img_url.startswith('/'): img_url = 'https://www.styleonme.com' + img_url
            
        img_response = requests.get(img_url, headers=headers, timeout=10)
        if img_response.status_code == 200:
            return BytesIO(img_response.content)
    except Exception:
        pass
    return None

# ==========================================
# Streamlit UI 및 메인 로직
# ==========================================
st.title("구글 시트 -> PDF 변환기")

# 세션 상태 초기화
if 'sheet_tabs' not in st.session_state:
    st.session_state['sheet_tabs'] = []

st.subheader("1. 데이터 소스 설정")
sheet_url = st.text_input(
    "구글 시트 URL", 
    value="https://docs.google.com/spreadsheets/d/1tHS8ZFlSCXkWuUD-engpuQXaCNSWdK598Vm-ccELGPc/edit?usp=sharing"
)

if st.button("시트 탭 불러오기"):
    try:
        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive.readonly']
        creds = get_creds()
        client = gspread.authorize(creds)
        client = gspread.authorize(creds)
        
        sheet_id = sheet_url.split('/d/')[1].split('/')[0]
        spreadsheet = client.open_by_key(sheet_id)
        
        st.session_state['sheet_tabs'] = [ws.title for ws in spreadsheet.worksheets()]
        st.success("시트 탭 목록을 성공적으로 불러왔다.")
    except Exception as e:
        st.error(f"오류 발생: {e}")

if st.session_state['sheet_tabs']:
    selected_tab = st.selectbox("가져올 시트 탭 선택", st.session_state['sheet_tabs'])
    
    st.subheader("2. 작업 실행")
    if st.button("PDF 렌더링 시작"):
        # 진행률 표시줄 및 상태 컨테이너
        progress_bar = st.progress(0)
        status_text = st.empty()
        log_container = st.container()
        
        try:
            status_text.text("구글 시트 데이터 로드 중...")
            scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive.readonly']
            creds = get_creds()
            client = gspread.authorize(creds)
            client = gspread.authorize(creds)
            spreadsheet = client.open_by_key(sheet_url.split('/d/')[1].split('/')[0])
            worksheet = spreadsheet.worksheet(selected_tab)
            all_values = worksheet.get_all_values()

            header_idx = -1
            for i, row in enumerate(all_values):
                if len(row) > 0 and str(row[0]).strip() == '순서':
                    header_idx = i
                    break
                    
            if header_idx == -1:
                st.error("A열에서 '순서'라는 값을 찾을 수 없다.")
                st.stop()

            headers = all_values[header_idx]
            raw_data = all_values[header_idx + 1:]

            valid_data = []
            empty_count = 0
            for row in raw_data:
                col_a_val = str(row[0]).strip() if len(row) > 0 else ""
                if not col_a_val:
                    empty_count += 1
                else:
                    empty_count = 0
                valid_data.append(row)
                if empty_count >= 5:
                    valid_data = valid_data[:-5]
                    with log_container:
                        st.info("A열 연속 5회 공백 감지. 로드 중단.")
                    break

            if not valid_data:
                st.error("유효한 데이터가 없다.")
                st.stop()

            processed_data = []
            for r in valid_data:
                row_data = r + [''] * (len(headers) - len(r))
                processed_data.append(row_data[:len(headers)])

            df = pd.DataFrame(processed_data, columns=headers)
            df['순서'] = df['순서'].replace(r'^\s*$', pd.NA, regex=True).ffill()
            df = df.dropna(subset=['순서'])

            # 폰트 등록
            status_text.text("폰트 등록 및 문서 구조 초기화 중...")
            if not os.path.exists(FONT_REGULAR):
                st.error("malgun.ttf 파일이 존재하지 않는다.")
                st.stop()
            pdfmetrics.registerFont(TTFont('Malgun', FONT_REGULAR))
            
            bold_font_name = 'Malgun-Bold'
            if os.path.exists(FONT_BOLD):
                pdfmetrics.registerFont(TTFont('Malgun-Bold', FONT_BOLD))
            else:
                bold_font_name = 'Malgun'

            PAGE_WIDTH, PAGE_HEIGHT = 1920, 1080
            MARGIN = 50
            AVAIL_WIDTH = PAGE_WIDTH - (MARGIN * 2)
            AVAIL_HEIGHT = PAGE_HEIGHT - (MARGIN * 2)

            pdf_buffer = BytesIO()
            doc = SimpleDocTemplate(pdf_buffer, pagesize=(PAGE_WIDTH, PAGE_HEIGHT), 
                                    rightMargin=MARGIN, leftMargin=MARGIN, 
                                    topMargin=MARGIN, bottomMargin=MARGIN)
            styles = getSampleStyleSheet()

            style_left_43_bold = ParagraphStyle('L43B', parent=styles['Normal'], fontName=bold_font_name, fontSize=43, leading=50, alignment=TA_LEFT)
            style_left_32_bold = ParagraphStyle('L32B', parent=styles['Normal'], fontName=bold_font_name, fontSize=32, leading=40, alignment=TA_LEFT)
            style_right_35 = ParagraphStyle('R35', parent=styles['Normal'], fontName='Malgun', fontSize=35, leading=42, alignment=TA_RIGHT)
            style_right_31 = ParagraphStyle('R31', parent=styles['Normal'], fontName='Malgun', fontSize=31, leading=37, alignment=TA_RIGHT)
            style_right_28 = ParagraphStyle('R28', parent=styles['Normal'], fontName='Malgun', fontSize=28, leading=34, alignment=TA_RIGHT)

            story = []
            story.append(PageBreak())

            grouped = df.groupby('순서', sort=False)
            total_groups = len(grouped)

            for i, (order_val, group_df) in enumerate(grouped):
                status_text.text(f"순서 {order_val} 처리 중... ({i+1}/{total_groups})")
                progress_bar.progress((i + 1) / total_groups)
                images_data = []

                order_str = str(order_val)
                if not order_str.endswith('번'): order_str += '번'
                    
                left_story = []
                left_story.append(Paragraph(order_str, style_left_43_bold))
                left_story.append(Spacer(1, 23))
                left_story.append(Paragraph("코디 진행 목록", style_left_32_bold))

                right_story = []
                for index, row in group_df.iterrows():
                    name = str(row.get('상품명', ''))
                    color = str(row.get('색상', ''))
                    size = str(row.get('사이즈', ''))
                    
                    price_str = str(row.get('라방가격', '0')).replace(',', '').strip()
                    try:
                        price = f"\\{int(price_str):,}"
                    except ValueError:
                        price = price_str
                        
                    mix = str(row.get('혼용률', ''))
                    dims_raw = str(row.get('치수', ''))
                    dims = "" if dims_raw.strip() == '' else dims_raw.replace('?', '').replace('\n', '<br/>')
                        
                    line1 = f'<font color="#18A524">✔</font> <font color="#000000">{name}</font>'
                    line2 = f'<font color="#7030A0">{mix}</font>  <font color="#FF4B33">{color}</font>  <font color="#548235">{size}</font>  <font color="#2B78E4">{price}</font>'
                    line3 = f'<font color="#007060">{dims}</font>'

                    right_story.append(Paragraph(line1, style_right_35))
                    right_story.append(Spacer(1, 7))
                    right_story.append(Paragraph(line2, style_right_31))
                    right_story.append(Spacer(1, 7))
                    right_story.append(Paragraph(line3, style_right_28))
                    right_story.append(Spacer(1, 17))

                    site_url = str(row.get('사이트링크', ''))
                    if site_url and site_url.strip() != '':
                        img_data = get_image_from_url(site_url)
                        if img_data:
                            images_data.append(img_data)
                            with log_container:
                                st.write(f"✅ 이미지 크롤링 성공: {site_url}")
                        else:
                            with log_container:
                                st.write(f"❌ 이미지 크롤링 실패: {site_url}")

                col_left_width = AVAIL_WIDTH * 0.25
                col_right_width = AVAIL_WIDTH * 0.75

                main_table = Table([[left_story, right_story]], colWidths=[col_left_width, col_right_width])
                main_table.setStyle(TableStyle([
                    ('VALIGN', (0,0), (-1,-1), 'TOP'),
                    ('ALIGN', (0,0), (0,0), 'LEFT'),
                    ('ALIGN', (1,0), (1,0), 'RIGHT'),
                    ('LEFTPADDING', (0,0), (-1,-1), 0),
                    ('RIGHTPADDING', (0,0), (-1,-1), 0),
                    ('TOPPADDING', (0,0), (-1,-1), 0),
                    ('BOTTOMPADDING', (0,0), (-1,-1), 0),
                ]))
                
                w, table_h = main_table.wrap(AVAIL_WIDTH, AVAIL_HEIGHT)
                remaining_h = AVAIL_HEIGHT - table_h

                story.append(main_table)

                if images_data:
                    story.append(AbsoluteBottomRightImages(images_data, remaining_h))

                story.append(PageBreak())

            status_text.text("PDF 렌더링 중...")
            doc.build(story)
            pdf_buffer.seek(0)
            
            st.success("PDF 생성이 완료되었다.")
            st.download_button(
                label="📥 완료된 PDF 다운로드",
                data=pdf_buffer,
                file_name="코디진행목록_결과.pdf",
                mime="application/pdf"
            )
            
        except Exception as e:
            st.error(f"작업 중 치명적인 오류 발생: {e}")
