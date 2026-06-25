// Passive: Extract and send basic metadata (Thin Payload)
function sendThinPayload() {
  const metadata = {
    type: "THIN_PAYLOAD",
    url: window.location.href,
    title: document.title,
    channelName: ""
  };
  
  if (window.location.hostname.includes("youtube.com")) {
    const channelElement = document.querySelector("#text.ytd-channel-name");
    if (channelElement) {
      metadata.channelName = channelElement.innerText;
    }
  }

  chrome.runtime.sendMessage(metadata);
}

// Active: Listen for SCRAPE_DOM commands to extract text (Fat Payload)
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.command === "SCRAPE_DOM") {
    let text = document.body.innerText || "";
    text = text.substring(0, 3000); // Cap at 3000 chars
    
    sendResponse({
      type: "FAT_PAYLOAD",
      text: text,
      url: window.location.href
    });
  }
});

// Run passive on load
setTimeout(() => {
  if (!document.hidden) {
    sendThinPayload();
  }
}, 1000); // Small delay to let page load
