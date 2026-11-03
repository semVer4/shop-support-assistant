const messages = document.querySelector('#messages');
const form = document.querySelector('#chat-form');
const input = document.querySelector('#question');
const error = document.querySelector('#error');
const send = document.querySelector('#send');
const mode = document.querySelector('#mode');
let pending = false;
const labels = {product: 'товар', delivery: 'доставка', return: 'возврат', opened: 'вскрытая упаковка', defect: 'брак', discount: 'скидки'};

function addMessage(role, text, sources = []) {
  const item = document.createElement('article');
  item.className = `message ${role}`;
  const name = document.createElement('p');
  name.className = 'author'; name.textContent = role === 'user' ? 'Вы' : 'Помощник';
  const answer = document.createElement('p');
  answer.className = 'answer'; answer.textContent = text;
  item.append(name, answer);
  if (sources.length) {
    const details = document.createElement('p');
    details.className = 'sources';
    details.textContent = `Регламент: ${sources.map(id => labels[id] ?? id).join(', ')}`;
    item.append(details);
  }
  messages.append(item); messages.scrollTop = messages.scrollHeight;
}

async function ask(question) {
  if (pending || !question.trim()) return;
  pending = true; error.textContent = ''; send.disabled = true;
  document.querySelectorAll('[data-question]').forEach(button => button.disabled = true);
  send.textContent = 'Отвечаю…';
  addMessage('user', question);
  try {
    const response = await fetch('/api/chat', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({message: question}), signal: AbortSignal.timeout(22000)});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Не удалось получить ответ');
    addMessage('assistant', data.answer, data.sources);
    mode.textContent = data.mode === 'llm+policy' ? 'LLM разбирает вопрос · ответ проверяется по регламенту' : data.mode === 'rules-fallback' ? 'LLM недоступна · ответ сформирован автономно по регламенту' : 'Автономный режим · без вызовов LLM';
    input.value = '';
  } catch (problem) {
    error.textContent = problem.name === 'TimeoutError' ? 'Ответ не получен вовремя. Попробуйте ещё раз.' : problem.message;
  } finally {
    pending = false; send.disabled = false; send.textContent = 'Отправить';
    document.querySelectorAll('[data-question]').forEach(button => button.disabled = false);
    input.focus();
  }
}

form.addEventListener('submit', event => { event.preventDefault(); ask(input.value.trim()); });
document.querySelectorAll('[data-question]').forEach(button => button.addEventListener('click', () => { input.value = button.dataset.question; ask(input.value); }));
addMessage('assistant', 'Здравствуйте! Что хотите узнать о наушниках X1, доставке или возврате?');
Promise.all([fetch('/api/health').then(r => r.json()), fetch('/api/policy').then(r => r.json())]).then(([health, policy]) => {
  mode.textContent = health.mode === 'llm+policy' ? 'LLM подключена · ответ проверяется по регламенту' : 'Автономный режим · без вызовов LLM';
  for (const rule of policy.knowledge_base.rules) {
    const item = document.createElement('li'); item.textContent = rule.text; document.querySelector('#rules').append(item);
  }
  document.querySelector('#prompt').textContent = policy.system_prompt;
}).catch(() => { mode.textContent = 'Не удалось подключиться к серверу'; });

