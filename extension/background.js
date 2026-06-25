let socket = null;
const wsUrl = "wss://localhost:8765";

function connect() {
  socket = new WebSocket(wsUrl);
  
  socket.onopen = () => {
    console.log("Connected to AI Tutor Backend");
    sendActiveTabContext();
  };
  
  socket.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      if (msg.command === "SCRAPE_DOM") {
        chrome.tabs.query({active: true, currentWindow: true}, (tabs) => {
          if (tabs.length > 0) {
            chrome.tabs.sendMessage(tabs[0].id, {command: "SCRAPE_DOM"}, (response) => {
              if (response && response.type === "FAT_PAYLOAD") {
                socket.send(JSON.stringify(response));
              }
            });
          }
        });
      }
    } catch (e) {
      console.error("Error parsing message", e);
    }
  };
  
  socket.onclose = () => {
    console.log("Disconnected. Reconnecting in 5s...");
    setTimeout(connect, 5000);
  };
  
  socket.onerror = (err) => {
    console.error("WebSocket Error:", err);
  };
}

// Forward messages from content scripts to WebSocket
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "THIN_PAYLOAD" && socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify(message));
  }
});

function sendActiveTabContext() {
  if (!socket || socket.readyState !== WebSocket.OPEN) return;
  chrome.tabs.query({active: true, currentWindow: true}, (tabs) => {
    if (tabs.length > 0) {
      const tab = tabs[0];
      if (tab.url && tab.title) {
        const payload = {
          type: "THIN_PAYLOAD",
          url: tab.url,
          title: tab.title,
          channelName: "" // Only content script can read deep DOM, but this gets basic context instantly
        };
        socket.send(JSON.stringify(payload));
      }
    }
  });
}

// Trigger when the user switches tabs
chrome.tabs.onActivated.addListener(sendActiveTabContext);

// Trigger when the user switches browser windows
chrome.windows.onFocusChanged.addListener((windowId) => {
  if (windowId !== chrome.windows.WINDOW_ID_NONE) {
    sendActiveTabContext();
  }
});

connect();
