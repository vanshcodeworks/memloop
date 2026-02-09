document.addEventListener('DOMContentLoaded', () => {
    
    // --- 1. Typewriter Effect for Hero Terminal ---
    const commands = [
        { text: "pip install memloop", class: "cmd" },
        { text: "Downloading packages...", class: "log", delay: 500 },
        { text: "Installing engine v0.1.0...", class: "log", delay: 800 },
        { text: "Success. Neural link established.", class: "success", delay: 1200 },
        { text: "memloop start", class: "cmd blink-wait" }
    ];

    const typeWriterOutput = document.getElementById('typewriter-output');
    
    async function runTypewriter() {
        for (let line of commands) {
            const lineEl = document.createElement('div');
            lineEl.className = 'term-line';
            
            // Add prompt for commands
            if (line.class.includes('cmd')) {
                const prompt = document.createElement('span');
                prompt.className = 'prompt';
                prompt.textContent = "$ ";
                prompt.style.color = "#00f3ff";
                lineEl.appendChild(prompt);
            }

            typeWriterOutput.appendChild(lineEl);
            
            // Type out text char by char
            const textSpan = document.createElement('span');
            textSpan.className = line.class;
            lineEl.appendChild(textSpan);

            for (let char of line.text) {
                textSpan.textContent += char;
                await new Promise(r => setTimeout(r, 40)); // Typing speed
            }

            // Wait if there's a delay logic (simulation of processing)
            if (line.delay) {
                await new Promise(r => setTimeout(r, line.delay));
            } else {
                await new Promise(r => setTimeout(r, 300)); // Natural pause after typing
            }
        }
    }

    // Start typing after a short delay
    setTimeout(runTypewriter, 1000);

    // --- 2. Intersection Observer (Scroll Animations) ---
    const observerOptions = {
        threshold: 0.1,
        rootMargin: "0px"
    };

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
                observer.unobserve(entry.target); // Only animate once
            }
        });
    }, observerOptions);

    document.querySelectorAll('.fade-in, .fade-up').forEach(el => {
        observer.observe(el);
    });

    // --- 3. Tabs Logic ---
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabPanes = document.querySelectorAll('.tab-pane');

    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            // Remove active class from all
            tabBtns.forEach(b => b.classList.remove('active'));
            tabPanes.forEach(p => p.classList.remove('active'));

            // Add to clicked
            btn.classList.add('active');
            const tabId = btn.getAttribute('data-tab');
            document.getElementById(tabId).classList.add('active');
        });
    });

});

// Global function for the copy button
function copyInstall() {
    navigator.clipboard.writeText('pip install memloop');
    const btn = document.querySelector('.btn-primary');
    const originalText = btn.innerHTML;
    
    btn.innerHTML = 'Copied! <span class="copy-icon">✓</span>';
    btn.style.borderColor = '#00ff9d';
    btn.style.color = '#00ff9d';

    setTimeout(() => {
        btn.innerHTML = originalText;
        btn.style.borderColor = '';
        btn.style.color = '';
    }, 2000);
}
