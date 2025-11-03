const listenBtn = document.getElementById('listenBtn');
const stopBtn = document.getElementById('stopBtn');
const transcriptEl = document.getElementById('transcript');
const planList = document.getElementById('planList');
const actionsBox = document.getElementById('actions');
const textInput = document.getElementById('textInput');
const sendText = document.getElementById('sendText');
const autoRunActions = document.getElementById('autoRunActions');

let recognition = null;
let isListening = false;

function supportsSpeechRecognition() {
  return 'webkitSpeechRecognition' in window || 'SpeechRecognition' in window;
}

function speak(text) {
  if (!('speechSynthesis' in window)) return;
  const utter = new SpeechSynthesisUtterance(text);
  utter.rate = 1.0;
  utter.pitch = 1.0;
  utter.lang = 'en-US';
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(utter);
}

function clearUI() {
  planList.innerHTML = '';
  actionsBox.innerHTML = '';
}

function renderPlan(steps) {
  planList.innerHTML = '';
  if (!steps || steps.length === 0) return;
  steps.forEach((s) => {
    const li = document.createElement('li');
    li.textContent = s;
    planList.appendChild(li);
  });
}

function addActionItem(label, url, type) {
  const div = document.createElement('div');
  div.className = 'action-item';
  const left = document.createElement('div');
  const right = document.createElement('div');
  right.className = 'action-buttons';

  const title = document.createElement('div');
  title.textContent = label;
  const badge = document.createElement('span');
  badge.className = 'badge ' + (type === 'safe' ? 'badge-good' : 'badge-warn');
  badge.textContent = type === 'safe' ? 'safe' : 'external';
  left.appendChild(title);
  left.appendChild(badge);

  const openBtn = document.createElement('button');
  openBtn.className = 'secondary';
  openBtn.textContent = 'Open';
  openBtn.onclick = () => window.open(url, '_blank');

  right.appendChild(openBtn);
  div.appendChild(left);
  div.appendChild(right);
  actionsBox.appendChild(div);

  if (autoRunActions.checked) {
    window.open(url, '_blank');
  }
}

async function sendToAgent(text) {
  clearUI();
  transcriptEl.textContent = text;
  try {
    const res = await fetch('/api/agent.py', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: text })
    });
    if (!res.ok) throw new Error('Agent HTTP ' + res.status);
    const data = await res.json();

    renderPlan(data.steps || []);
    if (data.speechResponse) speak(data.speechResponse);

    if (data.telLink) addActionItem('Call via phone dialer', data.telLink, 'safe');
    if (data.mapsUrl) addActionItem('Open Google Maps', data.mapsUrl, 'external');
    if (data.calendarUrl) addActionItem('Add to Calendar', data.calendarUrl, 'external');
    if (data.openUrl) addActionItem('Open link', data.openUrl, 'external');

  } catch (e) {
    console.error(e);
    speak('Sorry, I encountered an error.');
  }
}

function startListening() {
  if (!supportsSpeechRecognition()) {
    speak('Microphone not supported. Please type your command.');
    return;
  }
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  recognition = new SR();
  recognition.lang = 'en-US';
  recognition.interimResults = true;
  recognition.continuous = true;

  let finalTranscript = '';

  recognition.onresult = (event) => {
    let interim = '';
    for (let i = event.resultIndex; i < event.results.length; ++i) {
      const transcript = event.results[i][0].transcript;
      if (event.results[i].isFinal) finalTranscript += transcript;
      else interim += transcript;
    }
    transcriptEl.textContent = finalTranscript || interim;
  };

  recognition.onerror = (e) => {
    console.error('Speech error', e);
    stopListening();
  };

  recognition.onend = async () => {
    isListening = false;
    listenBtn.disabled = false;
    stopBtn.disabled = true;
    const text = (transcriptEl.textContent || '').trim();
    if (text) await sendToAgent(text);
  };

  recognition.start();
  isListening = true;
  listenBtn.disabled = true;
  stopBtn.disabled = false;
}

function stopListening() {
  if (recognition && isListening) {
    recognition.stop();
  }
}

listenBtn.addEventListener('click', startListening);
stopBtn.addEventListener('click', stopListening);
sendText.addEventListener('click', () => {
  const text = (textInput.value || '').trim();
  if (text) sendToAgent(text);
});

textInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') {
    const text = (textInput.value || '').trim();
    if (text) sendToAgent(text);
  }
});
