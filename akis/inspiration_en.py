"""English texts of the inspiration ideas (akis.inspiration_service), by idea key.

Each entry: (title, hook, description, shots, prompt). The Turkish texts in inspiration_service stay the
source; categories, platforms and templates are shared keys and are translated where they are shown.
"""

CATEGORIES = {
    'Hikâye anlatımı': 'Storytelling', 'Ürün / tanıtım': 'Product / promo', 'Eğitim': 'Education',
    'Vlog / günlük': 'Vlog / daily life', 'Trend / eğlence': 'Trends / fun', 'Sinematik': 'Cinematic',
}

IDEAS = {
    'sonu-basa': (
        'Start with the ending',
        'Open on the most striking frame of the video, then rewind with "So how did this happen?"',
        'Puts the finale in the first seconds and keeps viewers curious until the end.',
        ('0–3 s: the most striking moment', 'Rewind effect and title', 'How it all started',
         'The middle, where tension builds', 'The full finale'),
        'Put the most striking moment of the video in the first 3 seconds, then tell the story from the start. '
        'Cut the silences, keep transitions fast and show the finale again in the last scene.'),
    'bir-gunde': (
        'A city in 24 hours',
        'Start with a 06:00 clock caption and jump to a short scene every hour.',
        'Tells a whole day in short, time-stamped scenes.',
        ('06:00 wake-up and first coffee', 'Morning commute', 'Lunchtime food shots', 'Golden hour',
         'Night lights and the close'),
        'Split the video into short scenes in chronological order, put a time caption at the start of each scene, '
        'drop the empty parts and bring the total length down to 45 seconds.'),
    'once-sonra': (
        'Before / after transformation',
        'Show the same framing as "before" and "after", side by side or with a sudden cut.',
        'A shareable format that tells a transformation in one clear comparison.',
        ('"Before", fixed framing', 'Quick glimpses of the work', 'A sudden transition',
         '"After", same framing', 'A short reaction or result caption'),
        'Place the start and end shots back to back with the same framing, sum up the process in between with short '
        'sped-up clips and hold the "after" frame for 3 seconds at the end.'),
    'tek-plan-sir': (
        'One question, one secret',
        'Talk straight to the camera: "Here is what nobody tells you…"',
        'A short single-take story that opens with a line that sparks curiosity.',
        ('A curious line straight to camera', 'A visual that backs it up', 'The actual information',
         'A short example', 'Close with a question'),
        'Cut the pauses and repetitions in the speech, move the first sentence to the start, add large readable captions '
        'and keep it under 40 seconds.'),
    'acilis-kutusu': (
        'Mystery box opening',
        'A closed box, slow music and the moment a hand lifts the lid.',
        'Presents the product like a surprise and strengthens the first impression.',
        ('Closed box, close-up', 'The lid opening', 'First look at the product', 'Detail shots',
         'Product name and a short note'),
        'Slow down the unboxing, hit the music the moment the product appears, then show the details in quick cuts '
        'and write the product name at the end.'),
    'uc-ozellik': (
        'Three features, three seconds',
        'Start by counting down from feature number three.',
        'Counts down a product\'s three strongest points with rhythmic cuts.',
        ('Title: 3 features', 'Feature 3, quick demo', 'Feature 2, quick demo', 'Feature 1, the most impressive',
         'Call to action: where to buy'),
        'Make each feature its own 3 to 4 second clip, put a number over each, save the strongest feature for last '
        'and keep the pace high.'),
    'paket-hikayesi': (
        'An order\'s journey',
        'A small journey from preparing the package to delivery.',
        'A behind-the-scenes promo that builds trust for small businesses.',
        ('Preparing the product', 'Packing details', 'Handing it to the courier', 'The customer opening it',
         'Thank-you card'),
        'Combine the preparation and packing scenes in warm colours, cut the waiting and show the customer\'s reaction '
        'at the end.'),
    'musteri-yorumu': (
        'Promo in the customer\'s words',
        'Show a customer quote in large text, then match the product to that quote.',
        'Builds social proof by pairing reviews with footage.',
        ('Review quote in large text', 'The product in use', 'A second review', 'A detail shot', 'Brand close'),
        'Pick the strongest sentences from the recorded reviews, pair each with matching product footage and add captions.'),
    '60-sn-ders': (
        'One idea in 60 seconds',
        'Start a timer with "You\'ll learn this in 60 seconds."',
        'A lesson that explains one idea against the clock.',
        ('Timer and question', 'The definition in one sentence', 'A simple example', 'A common mistake', 'Summary card'),
        'Focus on one topic, add a short heading to each spoken section, cut the pauses and fit the whole thing into '
        '60 seconds.'),
    'adim-adim': (
        'How to, step by step',
        'Show the finished result first, then say "now let\'s make it together".',
        'A tutorial that shows the result first and then goes through numbered steps.',
        ('The finished result', 'What you need', 'Step 1', 'Step 2', 'Step 3 and final check',
         'Summary and an invitation to ask'),
        'Put the result at the start, separate each step with a numbered heading, cut waiting and false starts and '
        'zoom in on the important parts.'),
    'mit-gercek': (
        'Myth or fact?',
        'Start with the caption "We\'ve always got this wrong."',
        'A quick, fun format that busts a common misconception.',
        ('The myth as a caption', 'A short twist', 'Proof of the fact', 'A simple visual explanation',
         'Summary of the facts'),
        'Show the myth on screen, then explain the truth in one clear clip, make the captions stand out and keep a '
        'medium pace.'),
    'ekran-kaydi': (
        'Screen recording mini guide',
        'Start with the screen that shows the problem and make the fix\'s name the title.',
        'A short guide that trims a screen recording and highlights the important clicks.',
        ('The screen with the problem', 'Opening the menu', 'Changing the setting', 'Seeing the result', 'Tip card'),
        'Cut the waiting in the screen recording, zoom in on the important clicks, support the narration with captions '
        'and give a short summary at the end.'),
    'sabah-rutini': (
        'Morning routine, second by second',
        'Start with the alarm clock and move through the routine in rhythmic cuts.',
        'Shows an everyday routine with clean cuts in sync with the music.',
        ('Alarm clock', 'Making the bed', 'Coffee or breakfast', 'Getting ready', 'Out the door'),
        'Cut the routine to the beat of the music, drop the waiting, keep transitions fast and end on the shot of '
        'walking out the door.'),
    'haftalik-ozet': (
        'The week in review',
        'Monday to Sunday, one shot for each day.',
        'A warm vlog that wraps up a week with a heading for each day.',
        ('First shot on Monday', 'The hardest moment of the week', 'The funniest moment of the week', 'The weekend',
         'Plans for next week'),
        'Give each day a short heading, pick the best shots, use a warm colour tone and keep it under 2 minutes.'),
    'gezi-mini': (
        'A trip: 5 stops, 1 video',
        'Show five stops on a map, then cut to the first one.',
        'An easy-to-watch travel video that tells a trip stop by stop.',
        ('Map and list of stops', 'Stop 1: the view', 'Stop 2: food', 'Stop 3: a surprise', 'Stops 4–5: quick clips',
         'The way home'),
        'Split it into stops, write the place name at the start of each one, pick the best scenic shots and show all '
        'the stops in a quick recap at the end.'),
    'slayt-anilar': (
        'A memory film from photos',
        'Start with your favourite photo, then go in chronological order.',
        'Turns photos into an emotional memory film set to music.',
        ('Opening photo', 'A chronological selection', 'Close-ups of faces', 'A funny moment', 'A thank-you note'),
        'Line up the pictures at 2–3 seconds each, add soft transitions, fit them to the music and write a short note '
        'at the end.'),
    'sessiz-meydan': (
        'Silent challenge',
        'Start without a word, only captions and sound effects.',
        'A fun, wordless flow carried by pictures and captions.',
        ('The challenge as a caption', 'First attempt', 'A failed attempt', 'The successful attempt', 'Reaction shot'),
        'Mute the speech, speed up the attempts, add a funny sound-effect caption to the failures and show the '
        'successful attempt in slow motion at the end.'),
    'beklenti-gercek': (
        'Expectation vs reality',
        'Split the screen in two: expectation on the left, reality on the right.',
        'A much-shared comedy format that compares expectation with reality.',
        ('Expectation title', 'The perfect dream', 'Reality title', 'The funny reality', 'A short final reaction'),
        'Place the expectation and reality scenes one after the other, put a title over each, make the sound effects '
        'stand out and bring it down to 20 seconds.'),
    'hizli-tepki': (
        'Rapid-fire reactions',
        'Different reactions to the same event, one after another.',
        'Creates humour by lining up short reaction shots in rhythm.',
        ('The event itself', 'Reaction 1', 'Reaction 2', 'Reaction 3', 'The funniest reaction'),
        'Trim each reaction to 1–2 seconds, delete the repeated parts, put the funniest reaction last and add zoom '
        'accents.'),
    'altin-saat': (
        'Golden hour poem',
        'Start on a slow shot of the sun touching the horizon.',
        'A calm visual poem built on natural light and slow movement.',
        ('Wide landscape', 'Detail of the light', 'A human silhouette', 'Slow camera move', 'Fading close'),
        'Apply a cinematic colour style, use slow transitions, reduce speech and noise, bring the music forward and '
        'fade out slowly at the end.'),
    'sinematik-fragman': (
        'Personal trailer',
        'A trailer line such as "This summer, everything changes."',
        'Cuts everyday footage to the rhythm of a film trailer.',
        ('Trailer line', 'Introducing the character', 'Tension shots', 'Accelerating cuts', 'Title and date card'),
        'Cut the footage to a trailer rhythm, build the tension step by step, apply a cinematic colour and show a '
        'title card at the end.'),
    'yagmur-sehir': (
        'Rainy city',
        'A shot where raindrops on the glass fall out of focus and turn into lights.',
        'A wordless, rhythmic city-at-night video built on atmosphere.',
        ('Drops on the glass', 'Street lights', 'Reflections', 'People walking', 'Closing shot'),
        'Give it a cool, cinematic colour, join short clips on the beats of the music and soften the transitions.'),
    'merak-sorusu': (
        'A video that opens with a question',
        'A big question mark and a hint of the answer in the first frame.',
        'A curiosity format that asks the question in the first scene and saves the answer for the end.',
        ('Question and hint', 'Time to guess', 'Hint 2', 'Silence before the answer', 'Answer and explanation'),
        'Put the question in the first 3 seconds, save the answer for the very end, keep the parts in between short '
        'and show the speech with captions.'),
}
