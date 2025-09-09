export default function ContactPage() {
  async function handleSubmit() {
    await fetch('/api/send-email', { method: 'POST', body: JSON.stringify({ name: 'Ada', email: 'ada@example.com', message: 'Hi' }) });
  }
  return (<div><h1>Contact</h1><button onClick={handleSubmit}>Send</button></div>);
}
