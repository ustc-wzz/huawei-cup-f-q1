"""质量信号的流式压缩与可恢复缓存；与问题一保留相同转换公式。"""
from pathlib import Path
import csv,hashlib,json,lzma,math,os,tempfile,time
import pandas as pd

SCALAR_FIELDS = ['dsir_books', 'dsir_wiki', 'dsir_math',
                 'rps_doc_word_count', 'rps_doc_num_sentences', 'rps_doc_unigram_entropy',
                 'rps_doc_frac_unique_words', 'rps_doc_frac_no_alph_words',
                 'rps_doc_frac_chars_top_2gram', 'rps_doc_frac_chars_top_3gram',
                 'rps_lines_uppercase_letter_fraction', 'rps_lines_ending_with_terminal_punctution_mark',
                 'rps_lines_numerical_chars_fraction', 'rps_doc_mean_word_length']
MB_FIELDS = ['modernbert_cleanliness', 'modernbert_readability', 'modernbert_reasoning', 'modernbert_professionalism']
OUT_COLS = (['id', 'sub_path', 'domain'] + SCALAR_FIELDS +
            ['fineweb_edu', 'fluency_p1', 'ad_p1'] + MB_FIELDS +
            ['qurater_1', 'qurater_2', 'qurater_3', 'qurater_4',
             'n_chars', 'n_lines', 'n_url', 'frac_nonascii', 'snippet'])
NUM_COLS = [c for c in OUT_COLS if c not in ('id', 'sub_path', 'domain', 'snippet')]
CHUNK = 25000

def softmax(z):
    m = max(z); e = [math.exp(v - m) for v in z]; s = sum(e)
    return [v / s for v in e]

def to_float(v, fmt='%.6g'):
    if v is None: return ''
    if isinstance(v, (list, tuple)):
        if len(v) != 1: return ''
        v = v[0]
    try:
        f = float(v)
        return '' if f != f else fmt % f
    except Exception:
        return ''

def compress_record(obj, domain):
    row = {'id': obj.get('id', ''), 'sub_path': obj.get('sub_path', ''), 'domain': domain}
    for c in SCALAR_FIELDS:
        row[c] = to_float(obj.get(c))
    row['fineweb_edu'] = to_float(obj.get('fineweb_edu'))
    for src, dst in (('fluency_en', 'fluency_p1'), ('ad_en', 'ad_p1')):
        v = obj.get(src)
        row[dst] = ('%.6g' % softmax(v)[1]) if isinstance(v, (list, tuple)) and len(v) == 2 else to_float(v)
    for c in MB_FIELDS:
        v = obj.get(c)
        if isinstance(v, (list, tuple)) and len(v) >= 2:
            p = softmax(v); row[c] = '%.6g' % sum(k * pk for k, pk in enumerate(p))
        else:
            row[c] = to_float(v)
    v = obj.get('qurater')
    for k in range(4):
        row['qurater_%d' % (k + 1)] = to_float(v[k]) if isinstance(v, (list, tuple)) and k < len(v) else ''
    text = obj.get('content') or obj.get('text') or ''
    if text:
        n = len(text)
        row['n_chars'] = n; row['n_lines'] = text.count('\n') + 1
        row['n_url'] = text.count('http://') + text.count('https://') + text.count('www.')
        row['frac_nonascii'] = '%.4g' % (sum(1 for ch in text if ord(ch) > 127) / n)
        row['snippet'] = text[:200].replace('\r', ' ').replace('\n', ' ')
    else:
        row['n_chars'] = row['n_lines'] = row['n_url'] = row['frac_nonascii'] = row['snippet'] = ''
    return row

def norm_domain(s):
    s = str(s or 'unknown').lower().replace('redpajama', '').replace('_', '').replace('-', '').strip()
    return {'cc': 'commoncrawl', 'books': 'book', 'wiki': 'wikipedia'}.get(s, s)

def open_any(p):
    p = str(p)
    return lzma.open(p, 'rt', encoding='utf-8') if p.endswith('.xz') else open(p, 'r', encoding='utf-8')

EXPECTED_ROWS={'A1_sample':51230,'A2_arxiv':17523,'A3_github':203752}

def raw_signal_paths(data):
    data=Path(data)
    a1=[data/'slimpajama_quality_signal_sample.jsonl.xz']
    if not a1[0].is_file():
        a1=[data/'slimpajama_quality_signal_sample.jsonl']
    if not a1[0].is_file():
        a1=sorted(data.glob('slimpajama_quality_signal_sample.jsonl*/slimpajama_quality_signal_sample.jsonl'))
    extended=data/'slimpajama_quality_extended'
    def prefer_compressed(prefix):
        files={p.name.removesuffix('.xz'):p for p in extended.glob(prefix+'*.jsonl')}
        files.update({p.name.removesuffix('.xz'):p for p in extended.glob(prefix+'*.jsonl.xz')})
        return [files[k] for k in sorted(files)]
    return a1,prefer_compressed('arxiv_'),prefer_compressed('github_')

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def read_parts(parts):
    frame=pd.concat([pd.read_csv(p,encoding='utf-8') for p in parts],ignore_index=True)
    if frame.columns.tolist()!=OUT_COLS:raise ValueError('缓存字段不完整')
    for column in NUM_COLS:frame[column]=pd.to_numeric(frame[column],errors='coerce')
    return frame

def load_signals(cache,prefix,raw_paths,fixed_domain=None):
    """校验现有缓存；缺失、损坏或原始输入变化时以临时目录重建。"""
    cache=Path(cache);cache.mkdir(parents=True,exist_ok=True)
    raw_paths=list(map(Path,raw_paths))
    if not raw_paths or not all(p.is_file() for p in raw_paths):
        raise FileNotFoundError(f'{prefix}原始附件不完整，请重新完整解压本复现包')
    source_hashes={p.name:digest(p) for p in raw_paths}
    manifest_path=cache/f'{prefix}_manifest.json'
    parts=sorted(cache.glob(prefix+'_part*.csv.xz'))
    try:
        if not parts:raise ValueError('缺少缓存')
        if manifest_path.exists():
            info=json.loads(manifest_path.read_text(encoding='utf-8'))
            if info['schema']!=1 or info['sources']!=source_hashes:raise ValueError('缓存来源已变化')
            if {p.name:digest(p) for p in parts}!=info['parts']:raise ValueError('缓存校验失败')
        frame=read_parts(parts)
        if len(frame)!=EXPECTED_ROWS[prefix]:raise ValueError('缓存记录数不完整')
    except (ValueError,KeyError,OSError,EOFError,lzma.LZMAError) as error:
        print(f'[{prefix}] {error}，从原始附件生成缓存…',flush=True)
        with tempfile.TemporaryDirectory(prefix='.'+prefix+'-',dir=cache) as tmp:
            stage=Path(tmp);count=0;writer=None;stream=None
            try:
                for source in raw_paths:
                    with open_any(source) as source_stream:
                        for number,line in enumerate(source_stream,1):
                            if not line.strip():continue
                            try:record=json.loads(line)
                            except ValueError as exc:raise ValueError(f'原始数据损坏：{source.name}:{number}') from exc
                            if count%CHUNK==0:
                                if stream is not None:stream.close()
                                stream=lzma.open(stage/f'{prefix}_part{count//CHUNK+1:02d}.csv.xz','wt',encoding='utf-8',newline='')
                                writer=csv.DictWriter(stream,fieldnames=OUT_COLS);writer.writeheader()
                            domain=fixed_domain or norm_domain(record.get('_source_domain'))
                            writer.writerow(compress_record(record,domain));count+=1
                            if count%25000==0:print(f'[{prefix}] 已生成 {count:,} 条',flush=True)
            finally:
                if stream is not None:stream.close()
            if count!=EXPECTED_ROWS[prefix]:raise ValueError(f'{prefix}原始记录数异常：{count}，预期{EXPECTED_ROWS[prefix]}')
            new_parts=sorted(stage.glob('*.csv.xz'))
            frame=read_parts(new_parts)
            # Publish validated parts; the manifest is the last commit marker.
            names={p.name for p in new_parts}
            for p in new_parts:os.replace(p,cache/p.name)
            for p in parts:
                if p.name not in names:p.unlink()
        parts=sorted(cache.glob(prefix+'_part*.csv.xz'))
    info={'schema':1,'sources':source_hashes,'rows':len(frame),'parts':{p.name:digest(p) for p in parts}}
    temporary=manifest_path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(info,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    os.replace(temporary,manifest_path)
    print(f'[{prefix}] 缓存完整：{len(frame):,} 条',flush=True)
    return frame
