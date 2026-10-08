# Phase 1 — layer feedback and verification guide

## L0: Capture

OpenCV edges se large convex quadrilateral milne par perspective warp hota hai.
Boundary na mile to full image use hoti hai aur finding dikhti hai. Quality score
corrected crop par calculate hota hai: Laplacian variance blur proxy, average intensity
brightness proxy, near-white saturation fraction possible glare proxy hai.

Verify: `blurred.png` par `needs_rescan`; `perspective.png` par boundary detection aur
non-identity transform. Mobile device ke liye thresholds separately calibrate karein.

## L1: OCR

Tesseract full-page VIZ read karta hai. Lower-half long text bands ko raw-line mode
mein read karke MRZ candidates bante hain. Alternate crop readings bhi raw text mein
preserved hain. Parser exact 3×30, 2×36, 2×44 layout require karta hai; short line ko
padding dekar fake evidence nahi banata. Numeric dates/check positions par O/I/B
corrections hote hain; raw strings intact hain. Unspecified sex ke liye generated
MRZ mein `<` aur VIZ mein `X` use hota hai; parsed semantic value `X` hoti hai,
raw filler preserve hota hai. Yeh [ICAO Doc 9303 Part 4](https://www.icao.int/publications/Documents/9303_p4_cons_en.pdf)
ke MRZ/VIZ distinction ko follow karta hai.

VIZ MRZ se populate nahi hoti. Isliye DOB alteration ka independent comparison
possible hai. Confidence Tesseract line/word proxy hai; per-field calibrated confidence
model future improvement hai. Full-page + multiple crop calls CPU latency badhate hain.

Verify: clean sample mein raw/corrected fields inspect karein; `dob_altered.png`
mein MRZ DOB aur VIZ DOB different honi chahiye. Actual OCR tests engine ko execute
karte hain; successful parser tests ko image OCR accuracy nahi bolna hai.

## L2: Rules

Check-digit character values × repeating 7/3/1 weights ka sum modulo 10 hota hai.
Composite check multiple MRZ ranges ko join karke calculate hota hai. Failed checksum
processing ko stop nahi karta. DOB century ambiguous ho to printed four-digit date
chahiye; expiry nearest century inference explicitly finding mein expose hoti hai.

Name comparison word-order differences normalize karta hai; transliteration/fuzzy
name matching implemented nahi hai. Visa entry window aur permitted stay same concept
nahi hain, isliye overlong stay ko policy-review note milta hai, automatic invalidity nahi.

Mock SQLite lookup issuer+number hash use karta hai. Validation read-only hai; repeated
validation prior-sighting count increment nahi karti. Multi-identity face checks Phase 2
mein synthetic identity index ke saath integrate honge.

Verify: invalid composite checksum flag ho, expired fixture flag ho, fictional
`Z9000001` blacklist hit ho, `Z9000002` previously seen ho. Missing DB ko clear result
samajhne ki jagah unavailable finding milni chahiye.

## Reproducible evidence

- `python -m pytest backend/tests -q`: rules, image OCR, API and failure modes.
- `python scripts/verify_phase1.py`: eight generated development fixtures ka report.
- `reports/phase1_smoke.json`: measured scenarios and latency; synthetic-only evidence.

Agla phase L4 face verification + limited liveness hai. Current geometric avatar ko
real biometric identity ya liveness validation ke liye suitable sample nahi mana jayega.
