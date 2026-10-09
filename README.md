# CineGraph Semantic Movie Catalog

Ứng dụng Semantic Web để tìm kiếm phim, khám phá quan hệ trong đồ thị tri thức và chạy truy vấn SPARQL. Catalog chỉ giữ phim có bản ghi khớp chính xác theo IMDb ID trong cả ba nguồn IMDb, Kaggle và OMDb. Snapshot hiện tại có 3.651 phim.

## Chạy web từ snapshot hiện tại

Mở thư mục `C:\Users\Acer\Downloads\semantic_web` và chạy `run_server.bat` (hoặc `python app.py`). Launcher dùng graph hiện có với 3.651 phim. Dùng `run_server.bat --no-browser` nếu không muốn tự mở trình duyệt.

## Chạy lại pipeline demo

1. Cài Python 3.10 trở lên.
2. Mở thư mục project và chạy `run_demo.bat`.
3. Lần đầu chạy sẽ cài thư viện, tải dữ liệu công khai từ Kaggle và IMDb, tạo RDF/Turtle, kiểm tra graph bằng SHACL rồi mở web demo tại `http://127.0.0.1:5000`.

Các lần sau dùng lại file tải về và cache OMDb. Có thể chạy trực tiếp bằng lệnh:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:PYTHONPATH = "$PWD\src"
.venv\Scripts\python.exe -m cinegraph.cli demo
```

Để chỉ dựng graph mà chưa mở web, dùng `python -m cinegraph.cli ingest`. Dùng `python -m cinegraph.cli serve` để mở graph đã tạo. `crawler.py` hoặc lệnh `python -m cinegraph.cli crawl` chỉ tải các file thô IMDb/Kaggle, không gọi OMDb và không dựng graph.

## Nguồn dữ liệu và API

| Nguồn | Vai trò | Dữ liệu được dùng | Cách nạp |
|---|---|---|---|
| IMDb datasets | Catalog gốc và điều kiện chọn phim | IMDb ID, tiêu đề, năm, thời lượng, thể loại, điểm và số lượt bình chọn | Tải `title.basics.tsv.gz` và `title.ratings.tsv.gz` từ nguồn chính thức; ghép theo `tconst`, chỉ giữ phim có hơn 50.000 lượt bình chọn |
| Kaggle · The Movies Dataset | Nguồn hợp nhất thứ hai | Doanh thu, ngân sách, đạo diễn, dàn diễn viên và TMDB person ID trong credits | Tải `movies_metadata.csv` và `credits.csv` từ `rounakbanik/the-movies-dataset`; ghép chính xác qua IMDb ID |
| OMDb API | Nguồn hợp nhất thứ ba | Cốt truyện, poster, giải thưởng và các điểm đánh giá ngoài IMDb | Truy vấn IMDb ID; cache phản hồi để dùng lại. Chỉ phim có kết quả OMDb được đưa vào catalog cuối |
| Wikidata SPARQL/API | Liên kết dữ liệu và hồ sơ người | URI phim, người, thể loại; mô tả tiếng Anh, ngày sinh/mất, ảnh và Wikipedia của người | Người được nối qua TMDB person ID; thông tin hồ sơ lấy theo Wikidata URI và cache riêng |
| DBpedia SPARQL | Liên kết dữ liệu mở | URI đối ứng theo IMDb ID | Chỉ gắn `owl:sameAs`; không thêm phim hay ghi đè metadata |

Catalog cuối là phần giao theo IMDb ID của IMDb, Kaggle và OMDb. IMDb giữ ưu tiên cho thể loại và điểm IMDb; Kaggle cung cấp doanh thu, ngân sách, diễn viên và đạo diễn; OMDb cung cấp cốt truyện, poster, giải thưởng và các điểm đánh giá ngoài IMDb. Wikidata/DBpedia không thêm phim hay metadata phim; Wikidata cung cấp hồ sơ cơ bản riêng cho người đã được nối bằng TMDB person ID. Các trường Kaggle `genres`/`plot` và OMDb `BoxOffice` không được ghi vào catalog cuối.

Project dùng The Movies Dataset vì `movies_metadata.csv` có `imdb_id`, doanh thu, thể loại và mô tả; `credits.csv` có diễn viên/đạo diễn. Pipeline chỉ tải hai CSV này để có thể nối chính xác với catalog IMDb mà không phải tải các bảng user-rating lớn. Kaggle không tự thêm phim vào catalog. Những dòng Kaggle trùng IMDb ID được gộp vào cùng một phim; ID không khớp sẽ bị bỏ qua. Nếu muốn dùng CSV khác, đặt file vào `data/raw/kaggle/`; importer nhận một số tên cột phổ biến như `imdb_id`/`tconst`, `title`, `year`, `genres`, `revenue`, `cast` và `director`.

Luồng xử lý: (1) tải file IMDb/Kaggle, (2) tạo catalog nền từ phim IMDb có hơn 50.000 lượt bình chọn, (3) ghép Kaggle và OMDb theo IMDb ID, (4) chỉ giữ phim có mặt trong đủ cả ba nguồn, (5) thêm liên kết Wikidata/DBpedia và liên kết người/thể loại, (6) lấy hồ sơ cơ bản cho người đã nối qua Wikidata, (7) tạo JSON và RDF/Turtle. Snapshot hiện tại có 3.651 record phim; hồ sơ người không làm thay đổi số record phim.

### Chạy riêng từng bước

```powershell
# 1. Chỉ tải/crawl dữ liệu thô IMDb và Kaggle
.venv\Scripts\python.exe crawler.py

# Tạo file cấu hình local và nhập API key do OMDb cấp
Copy-Item .env.example .env
notepad .env

# 2. Sau khi điền OMDB_API_KEY trong file .env, hợp nhất nguồn,
#    gọi OMDb và dựng catalog JSON/RDF mà chưa mở web
$env:PYTHONPATH = "$PWD\src"
.venv\Scripts\python.exe -m cinegraph.cli ingest

# 3. Mở web demo từ graph đã tạo
.venv\Scripts\python.exe -m cinegraph.cli serve
```

OMDb cần API key. Sao chép `.env.example` thành `.env`, điền key vào `OMDB_API_KEY=...`; không commit file `.env`. Pipeline chỉ xét các phim đã khớp giữa IMDb và Kaggle; cache được dùng lại và chỉ ID chưa có phản hồi mới tiêu thụ request. `CINEGRAPH_OMDB_BATCH_SIZE` giới hạn số request mới trong mỗi lượt ingest. Catalog cuối chỉ giữ phim có dữ liệu OMDb; nếu thiếu API key thì ingest không tạo catalog ba nguồn.

## Cấu trúc project

```text
semantic_web/
├── app.py                         # launcher tương thích
├── crawler.py                     # tải riêng dữ liệu IMDb/Kaggle
├── run_demo.bat                   # cài dependency và chạy demo
├── requirements.txt
├── requirements-dev.txt           # dependency cho kiểm tra code
├── pyproject.toml                 # cấu hình Ruff
├── tests/                         # regression tests chạy offline
├── .env.example
├── ontology/
│   ├── cinegraph.ttl              # OWL ontology và Schema.org alignment
│   └── cinegraph.shacl.ttl        # SHACL shapes kiểm tra dữ liệu RDF
├── queries/                       # 5 SPARQL query mẫu
├── data/
│   ├── raw/imdb/                  # IMDb TSV tải về
│   ├── raw/kaggle/                # Kaggle CSV tải về/đặt thủ công
│   ├── cache/                     # cache OMDb, hồ sơ Wikidata người và liên kết Linked Data
│   ├── processed/movies.json      # catalog đã hợp nhất + field provenance
│   ├── rdf/movies.ttl             # graph đầu ra
│   └── reports/                   # pipeline report và SHACL RDF report
└── src/cinegraph/
    ├── config.py
    ├── vocabulary.py              # namespace RDF và URL nguồn dùng chung
    ├── cli.py
    ├── sources/                   # adapter riêng cho từng nguồn
    ├── transform/                 # hợp nhất và chuyển sang RDF
    └── web/
        ├── app.py                 # tạo Flask app
        ├── routes.py              # HTTP API và kiểm tra tham số
        ├── catalog.py             # RDF, tìm kiếm, cache và gợi ý phim
        ├── explorer.py            # thực thi câu hỏi SPARQL có tham số
        ├── queries.py             # các mẫu SELECT
        ├── vocabulary.py          # nhãn nguồn và trọng số quan hệ
        ├── text.py                # chuẩn hóa tìm kiếm
        ├── templates/
        └── static/
```

## Mô hình Semantic Web

- Mỗi phim, người và thể loại là một thực thể URI trong graph cục bộ.
- Ontology định nghĩa `Movie`, `Person`, `Actor`, `Director`, `Genre`, rating và provenance. Các lớp/phần dữ liệu phù hợp được căn chỉnh với Schema.org.
- Quan hệ chính: `cine:directedBy`, `cine:hasActor`, `cine:hasGenre`; gợi ý phim được giải thích bằng các nút dùng chung.
- Mỗi phim giữ `prov:wasDerivedFrom` và `dcterms:source`; các trường đã hợp nhất có nút provenance riêng.
- Pipeline thử tìm bản ghi Wikidata (`P345`) và DBpedia theo IMDb ID của phim rồi mới thêm `owl:sameAs`.
- Wikidata/DBpedia không bổ sung metadata phim; thông tin hồ sơ chỉ được gắn cho thực thể người đã nối chính xác.
- Diễn viên/đạo diễn được liên kết với Wikidata qua TMDB person ID (`P4985`) lấy từ file credits. Tên người không được dùng làm khóa nối.
- Hồ sơ người gồm mô tả tiếng Anh, ngày sinh/mất, ảnh và liên kết Wikipedia nếu Wikidata có các trường đó; cache nằm trong `data/cache/person-profiles.json`.
- Thể loại được nối với Wikidata khi nhãn tiếng Anh khớp duy nhất với một thực thể thuộc nhánh `film genre`; nhãn mơ hồ hoặc không hỗ trợ sẽ để ở dạng nội bộ.
- Các URI ngoài được gắn bằng `owl:sameAs`; trang TMDB của người cũng được giữ dưới `foaf:page`. Cache liên kết nằm trong `data/cache/linked-entities.json`.
- SHACL kiểm tra tiêu đề, ID IMDb, kiểu dữ liệu/nội dung rating, năm phát hành và kiểu thực thể trong các quan hệ phim–người–thể loại. Kết quả tóm tắt nằm trong `data/reports/pipeline.json`; báo cáo RDF nằm ở `data/reports/shacl-report.ttl`.
- `/sparql` nhận truy vấn `SELECT` cục bộ; các file `.rq` trong `queries/` là ví dụ để trình bày.

IMDb ID là khóa nối chính của phim giữa ba nguồn. TMDB person ID là khóa nối cho diễn viên/đạo diễn. Pipeline chỉ dùng tên để tìm thể loại Wikidata khi kết quả khớp duy nhất và được phân loại là thể loại phim; không ghép người bằng tên.

Các truy vấn mẫu gồm tìm phim theo thể loại, phim của đạo diễn, phim điểm cao, điểm trung bình/số phim theo thể loại và kiểm tra các thực thể đã có liên kết ngoài.

RDF builder dùng `Decimal` cho các literal `xsd:decimal` để SHACL kiểm tra nhất quán trước và sau khi serialize Turtle. Production shape yêu cầu đúng một IMDb ID; range của title/description là `rdf:langString` tương ứng với literal tiếng Anh. Báo cáo pipeline lưu sẵn vẫn phản ánh lần ingest trước; kết quả mới được ghi khi chạy lại `python -m cinegraph.cli ingest`.

## Kiểm tra và định dạng code

Các bài kiểm tra dùng dữ liệu nhỏ trong thư mục tạm, không gọi API và không ghi đè snapshot hiện tại.

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
$env:PYTHONPATH = "$PWD\src"
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\ruff.exe check src tests app.py crawler.py
.venv\Scripts\ruff.exe format --check src tests app.py crawler.py
```

Để áp dụng định dạng thống nhất, chạy `ruff format src tests app.py crawler.py`. Namespace và URL nguồn nằm trong `src/cinegraph/vocabulary.py`; các module web và RDF builder dùng cùng một định nghĩa.

## Đầu ra và kiểm tra trạng thái

- `data/processed/movies.json`: dữ liệu đã hòa giải và nguồn của từng trường.
- `data/rdf/movies.ttl`: ontology + instance graph Turtle.
- `data/reports/pipeline.json`: trạng thái nguồn, số phim sau bộ lọc ba nguồn, liên kết thực thể/hồ sơ người, SHACL và số triples.
- `/api/status`: báo cáo pipeline ở dạng JSON.
- `/health`: kiểm tra server và số triples đang nạp.

## Tìm kiếm và lọc phim

Catalog hỗ trợ kết hợp tên phim, thể loại, khoảng năm phát hành, điểm IMDb tối thiểu, tên đạo diễn và tên diễn viên. Có thể sắp xếp theo điểm IMDb, lượt bình chọn, năm, doanh thu hoặc tên phim. Endpoint `GET /api/movies` nhận các tham số `q`, `genre`, `year_from`, `year_to`, `min_rating`, `director`, `actor`, `sort` và `limit`; giao diện hiển thị tối đa 200 phim và báo tổng số kết quả phù hợp để người dùng thu hẹp bộ lọc khi cần.

IMDb datasets có điều khoản sử dụng riêng và được IMDb cung cấp cho mục đích cá nhân/phi thương mại. OMDb yêu cầu tuân thủ điều khoản API và attribution của dịch vụ. Kiểm tra license và điều khoản hiện hành của các nguồn trước khi phân phối dữ liệu đã tải cùng project.
