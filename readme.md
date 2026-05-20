# Vortex Engine & Service Report Generator

Dibuat untuk memenuhi kebutuhan laporan pada aplikasi **Vortex**. Dapat menghasilkan laporan dalam format:
- **PPTX**
- **XLSX**
- **DOCX**

Data untuk laporan diambil dari berbagai sumber:
- **ES**
- **PG**
- **EXTERNAL API**

## Flow 
- **ENGINE**
Engine akan melakukan *consume message* dari **RabbitMQ**. *Message* berisi id, tipe laporan dan rentang waktu, rentang waktu ini akan digunakan untuk pengambilan data ke database. Id akan di match ke mongo untuk kemudian digunakan untuk update status laporan dan s3 path.

- **SERVICE**
Service akan menembak EXTERNAL API untuk kemudian diambil response nya. Data dari response akan digunakan untuk pembuatan laporan(**DOCX**)

## HOW TO START
1 **Buat venv**
- python3 -m venv venv

2 **Aktifkan venv**
- source venv/bin/activate

3 **Install dependencies**
- pip install -r requirements.txt

4 **Jalankan engine atau service**
- untuk engine **python3 main.py -m engine**
- untuk service **python3 main.py -m service**