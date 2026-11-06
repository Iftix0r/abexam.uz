// Abjon's sounds, synthesised in the browser: no audio files to download.
// createSound() must run inside a user gesture, or browsers keep it silent.

export function createSound(given) {
  const ctx = given || new (window.AudioContext || window.webkitAudioContext)();
  const master = ctx.createGain();
  master.gain.value = 0.42;
  const limiter = ctx.createDynamicsCompressor();
  master.connect(limiter);
  limiter.connect(ctx.destination);

  const noiseBuffer = ctx.createBuffer(1, ctx.sampleRate, ctx.sampleRate);
  const samples = noiseBuffer.getChannelData(0);
  for (let i = 0; i < samples.length; i++) samples[i] = Math.random() * 2 - 1;

  function envelope(t, dur, gain) {
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(gain, t + Math.min(0.012, dur / 4));
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    g.connect(master);
    return g;
  }

  function tone(type, from, to, t, dur, gain) {
    const osc = ctx.createOscillator();
    osc.type = type;
    osc.frequency.setValueAtTime(from, t);
    osc.frequency.exponentialRampToValueAtTime(to, t + dur);
    osc.connect(envelope(t, dur, gain));
    osc.start(t);
    osc.stop(t + dur + 0.02);
    return osc;
  }

  function noise(t, dur, gain, filterType, from, to) {
    const src = ctx.createBufferSource();
    src.buffer = noiseBuffer;
    src.loop = true;
    const filter = ctx.createBiquadFilter();
    filter.type = filterType;
    filter.frequency.setValueAtTime(from, t);
    filter.frequency.exponentialRampToValueAtTime(to || from, t + dur);
    src.connect(filter);
    filter.connect(envelope(t, dur, gain));
    src.start(t);
    src.stop(t + dur + 0.02);
  }

  const thud = (t, gain) => {
    tone('sine', 150, 52, t, 0.13, gain);
    noise(t, 0.05, gain * 0.25, 'lowpass', 900);
  };
  const whoosh = (t, dur, gain) => noise(t, dur, gain, 'bandpass', 500, 2600);

  const sounds = {
    jump: t => tone('sine', 250, 720, t, 0.17, 0.55),
    land: t => thud(t, 0.6),
    leap(t, o) {
      tone('triangle', 230, 600, t, 0.22, 0.42);
      if (o.spins) whoosh(t + 0.1, 0.4 + 0.18 * o.spins, 0.3);
    },
    flip(t) {
      tone('sine', 250, 760, t, 0.2, 0.5);
      whoosh(t + 0.1, 0.62, 0.32);
      thud(t + 0.86, 0.5);
    },
    wave(t) {
      tone('sine', 640, 860, t, 0.09, 0.32);
      tone('sine', 860, 1120, t + 0.11, 0.1, 0.32);
    },
    read(t) {
      noise(t, 0.11, 0.55, 'bandpass', 2400, 1500);
      noise(t + 0.16, 0.09, 0.42, 'bandpass', 2600, 1700);
    },
    spin(t) {
      whoosh(t, 1.1, 0.6);
      whoosh(t + 1.2, 1.1, 0.6);
    },
    dance(t) {
      [523, 659, 784, 1047, 784, 659, 784, 1047].forEach((note, i) => {
        tone('triangle', note, note, t + i * 0.16, 0.14, 0.26);
      });
    },
    dizzy(t) {
      const osc = tone('sine', 620, 280, t, 1.2, 0.22);
      const wobble = ctx.createOscillator();
      const depth = ctx.createGain();
      wobble.frequency.value = 9;
      depth.gain.value = 110;
      wobble.connect(depth);
      depth.connect(osc.frequency);
      wobble.start(t);
      wobble.stop(t + 1.25);
    },
    tickle(t) {
      for (let i = 0; i < 6; i++) tone('sine', 860 + i * 45, 1260 + i * 45, t + i * 0.09, 0.07, 0.3);
    },
    angry(t) {
      for (const at of [0, 0.95]) {
        const osc = ctx.createOscillator();
        const filter = ctx.createBiquadFilter();
        osc.type = 'sawtooth';
        osc.frequency.setValueAtTime(92, t + at);
        osc.frequency.linearRampToValueAtTime(138, t + at + 0.28);
        osc.frequency.linearRampToValueAtTime(78, t + at + 0.7);
        filter.type = 'lowpass';
        filter.frequency.value = 760;
        osc.connect(filter);
        filter.connect(envelope(t + at, 0.72, 0.5));
        osc.start(t + at);
        osc.stop(t + at + 0.74);
      }
      for (let at = 0.08; at < 2.5; at += 0.32) thud(t + at, 0.36);
      noise(t + 0.4, 2.1, 0.07, 'highpass', 3200);
    },
    calm(t) {
      tone('sine', 520, 230, t, 0.75, 0.26);
      noise(t, 0.75, 0.05, 'lowpass', 1400, 500);
    },
    talk(t, o) {
      const count = Math.max(3, Math.min(8, o.count || 5));
      for (let i = 0; i < count; i++) {
        const pitch = 340 + Math.random() * 280;
        tone('triangle', pitch, pitch * 1.08, t + i * 0.085, 0.06, 0.2);
      }
    },
    step: t => tone('sine', 200, 120, t, 0.04, 0.1),
    wake(t) {
      tone('sine', 290, 540, t, 0.28, 0.24);
      tone('sine', 540, 370, t + 0.28, 0.3, 0.24);
    },
  };

  const lastPlayed = {};
  return {
    ctx,
    names: Object.keys(sounds),
    unlock() {
      if (ctx.state === 'suspended' && ctx.resume) ctx.resume();
    },
    play(name, options) {
      const now = ctx.currentTime;
      if (!sounds[name] || (lastPlayed[name] !== undefined && now - lastPlayed[name] < 0.09)) return;
      lastPlayed[name] = now;
      sounds[name](now + 0.005, options || {});
    },
  };
}
