So this morning we put the KnockOff pipeline through its paces, and I want to show you what we built.

First, we took a still photo of Simone Sanders, just a single JPEG, and used LivePortrait with a driver video to animate it. Head movements, eye movements, mouth movements, all generated from one photograph. That's the foundation.

Then we ran it through Wav2Lip for lip sync and got a talking head video in under 30 seconds. No cloud APIs, no subscriptions, everything running locally on an M4 Pro.

But here's where it got interesting. When we tried the portrait format for TikTok and YouTube Shorts, the framing was cutting me in half. So we built a face-aware crop using OpenCV to detect where the face actually is in the frame, then slice a perfect nine by sixteen window around it.

Then we hit a ghost mouth floating above my head. Turns out Wav2Lip caches face coordinates between runs, so Sanders' face data was bleeding into my video. Cleared the cache, problem solved.

The result? A production-ready portrait avatar pipeline. One photo in, animated talking head out, any aspect ratio. We call it TikTok Doug HEM. Head, eyes, mouth. And you're watching it right now.
