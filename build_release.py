"""Create a portable release archive, excluding installed dependencies and caches."""
from pathlib import Path
import hashlib,zipfile
ROOT=Path(__file__).resolve().parent
SKIP={'node_modules','__pycache__','.pytest_cache','.venv','.git'}
def files():
    return sorted(p for p in ROOT.rglob('*') if p.is_file() and not any(x in SKIP for x in p.relative_to(ROOT).parts)
        and p.suffix not in {'.pyc','.tsbuildinfo'} and p.name not in {'hackathon.zip','SHA256SUMS.txt'})
def main():
    selected=files()
    (ROOT/'SHA256SUMS.txt').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.relative_to(ROOT).as_posix()+'\n' for p in selected))
    output=ROOT.parent/'hackathon.zip'
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for p in selected+[ROOT/'SHA256SUMS.txt']:archive.write(p,'hackathon/'+p.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        assert not any('/node_modules/' in p for p in archive.namelist())
    print(f'{output} · {output.stat().st_size:,} bytes · {len(selected)+1} files')
if __name__=='__main__':main()
