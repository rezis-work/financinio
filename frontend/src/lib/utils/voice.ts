import { api } from '$lib/api/client';

export interface ActiveRecorder {
	stop: () => Promise<Blob>;
	cancel: () => void;
}

function pickSupportedAudioMime(): string {
	if (typeof MediaRecorder === 'undefined') return '';
	const candidates = [
		'audio/webm;codecs=opus',
		'audio/webm',
		'audio/mp4',
		'audio/ogg;codecs=opus'
	];
	for (const mime of candidates) {
		if (MediaRecorder.isTypeSupported(mime)) return mime;
	}
	return '';
}

export async function startAudioRecording(): Promise<ActiveRecorder> {
	if (
		typeof navigator === 'undefined' ||
		!navigator.mediaDevices ||
		!navigator.mediaDevices.getUserMedia
	) {
		throw new Error('Microphone recording is not supported in this browser.');
	}

	const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
	const mimeType = pickSupportedAudioMime();
	const recorder = mimeType
		? new MediaRecorder(stream, { mimeType })
		: new MediaRecorder(stream);

	const chunks: Blob[] = [];
	recorder.ondataavailable = (ev) => {
		if (ev.data && ev.data.size > 0) chunks.push(ev.data);
	};

	const stopTracks = () => {
		for (const track of stream.getTracks()) track.stop();
	};

	recorder.start(200);

	return {
		stop: () =>
			new Promise<Blob>((resolve, reject) => {
				recorder.onstop = () => {
					stopTracks();
					const finalType = recorder.mimeType || mimeType || 'audio/webm';
					const blob = new Blob(chunks, { type: finalType });
					if (blob.size === 0) {
						reject(new Error('No audio was captured. Try speaking a bit longer.'));
					} else {
						resolve(blob);
					}
				};
				recorder.onerror = () => {
					stopTracks();
					reject(new Error('Microphone recording interrupted.'));
				};
				if (recorder.state !== 'inactive') {
					recorder.stop();
				} else {
					stopTracks();
					resolve(new Blob(chunks, { type: mimeType || 'audio/webm' }));
				}
			}),
		cancel: () => {
			if (recorder.state !== 'inactive') {
				recorder.onstop = () => stopTracks();
				recorder.stop();
			} else {
				stopTracks();
			}
		}
	};
}

let activeAudioEl: HTMLAudioElement | null = null;
let activeAudioUrl: string | null = null;

export function stopSpeaking(): void {
	if (activeAudioEl) {
		activeAudioEl.pause();
		activeAudioEl.currentTime = 0;
		activeAudioEl = null;
	}
	if (activeAudioUrl) {
		URL.revokeObjectURL(activeAudioUrl);
		activeAudioUrl = null;
	}
	if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
		window.speechSynthesis.cancel();
	}
}

function stripMarkdownForBrowserSpeech(text: string): string {
	return text
		.replace(/\|[^\n]+\|/g, ' ')
		.replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
		.replace(/https?:\/\/\S+/g, '')
		.replace(/[#*_`~>]+/g, '')
		.replace(/\s+/g, ' ')
		.trim()
		.slice(0, 750);
}

export async function speakLunaText(
	text: string,
	onEnd?: () => void
): Promise<void> {
	stopSpeaking();
	try {
		const blob = await api.voiceSpeak(text, 'nova');
		const url = URL.createObjectURL(blob);
		const audio = new Audio(url);
		activeAudioEl = audio;
		activeAudioUrl = url;
		audio.onended = () => {
			stopSpeaking();
			onEnd?.();
		};
		audio.onerror = () => {
			stopSpeaking();
			onEnd?.();
		};
		await audio.play();
		return;
	} catch {
		// Graceful fallback to browser Web Speech Synthesis
		if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
			const clean = stripMarkdownForBrowserSpeech(text);
			if (!clean) {
				onEnd?.();
				return;
			}
			const utter = new SpeechSynthesisUtterance(clean);
			utter.rate = 1.02;
			utter.onend = () => onEnd?.();
			utter.onerror = () => onEnd?.();
			window.speechSynthesis.speak(utter);
		} else {
			onEnd?.();
		}
	}
}
