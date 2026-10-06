# Generated face asset provenance

Built-in **imagegen** tool use hua; CLI/API-key fallback use nahi hua.
Project asset: `assets/synthetic_faces.png`. Do fictional adult portraits ek contact
sheet mein generated hain. `generate_face_fixtures.py` deterministic OpenCV crop,
resize, slight rotation, brightness aur blur transformations se CV fixtures banata hai.
Original generated master retained hai. Koi real passport ya real-person portrait
source use nahi kiya gaya. AI output ki kisi real person se accidental resemblance
independently evaluate nahi ki gayi.

Final prompt (verbatim):

> Use case: scientific-educational. Asset type: a single synthetic face test contact sheet for a local computer-vision teaching demo. Generate a photorealistic horizontal diptych with two equally sized square panels, each with exactly one entirely fictional adult, head and shoulders, front-facing, neutral expression, eyes open and unobstructed, diffuse studio lighting, simple light gray background. Left panel: fictional adult with short dark wavy hair, narrow oval face, clean-shaven, charcoal crewneck. Right panel: a clearly different fictional adult with short auburn straight hair, rounder face, light freckles, olive crewneck. Both heads fully visible and centered with generous margins. A narrow straight divider exactly halfway across. Small legible text at bottom of each panel: SYNTHETIC A and SYNTHETIC B. Do not depict any real person or famous likeness. Do not include passport pages, ID numbers, official seals, or additional faces. This is one contact sheet, not multiple files.

Pair labels synthetic development assumptions hain. Same-person positive pair
independent camera sessions se collect nahi hui; shared-source transformations hain.
Yeh asset genuine-face training data ya liveness evidence nahi hai.
