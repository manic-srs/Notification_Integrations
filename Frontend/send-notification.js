/**
 * Wires up Notification.html's "Send a notification" form to the backend
 * (Backend/app/api/routes.py: POST /api/notifications). Shows the matching
 * destination field only once its channel checkbox is checked, then builds
 * the per-channel payload the backend's NotificationCreateRequest schema
 * requires (a `destination` for Teams/Slack, a `recipient` for Email).
 */
(function () {
  const form = document.getElementById("notification-form");
  const status = document.getElementById("form-status");
  const sendButton = form.querySelector(".send-button");

  document.querySelectorAll("[data-channel-toggle]").forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      const fields = document.querySelector(
        `[data-channel-fields="${checkbox.dataset.channelToggle}"]`
      );
      if (fields) fields.hidden = !checkbox.checked;
    });
  });

  function buildPayload() {
    const title = document.getElementById("subject").value.trim();
    const message = document.getElementById("message").value.trim();

    if (!title) throw new Error("Enter a title or subject.");
    if (!message) throw new Error("Enter a message.");

    return { title, message, channels: buildChannelsPayload() };
  }

  function buildChannelsPayload() {
    const channels = {};

    const teamsChecked = document.querySelector('[data-channel-toggle="teams"]').checked;
    const emailChecked = document.querySelector('[data-channel-toggle="email"]').checked;
    const slackChecked = document.querySelector('[data-channel-toggle="slack"]').checked;

    if (teamsChecked) {
      const destination = document.getElementById("teams-destination").value.trim();
      if (!destination) throw new Error("Enter a Teams destination.");
      channels.teams = [{ destination }];
    }
    if (emailChecked) {
      const recipient = document.getElementById("email-destination").value.trim();
      if (!recipient) throw new Error("Enter an Email recipient.");
      channels.email = [{ recipient, subject: document.getElementById("subject").value.trim() || null }];
    }
    if (slackChecked) {
      const destination = document.getElementById("slack-destination").value.trim();
      if (!destination) throw new Error("Enter a Slack destination.");
      channels.slack = [{ destination }];
    }

    if (Object.keys(channels).length === 0) {
      throw new Error("Select at least one channel.");
    }
    return channels;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    status.textContent = "";
    status.style.color = "";

    let payload;
    try {
      payload = buildPayload();
    } catch (validationError) {
      status.textContent = validationError.message;
      status.style.color = "#dc2626";
      return;
    }

    sendButton.disabled = true;
    sendButton.textContent = "Sending...";
    try {
      const notification = await NotificationApi.createNotification(payload);
      const summary = notification.deliveries
        .map((d) => `${d.channel}: ${NotificationUi.statusLabel(d.status)}`)
        .join(" · ");
      status.textContent = `Sent. ${summary}`;
      status.style.color = "#059669";
      form.reset();
      document.querySelectorAll(".channel-destination").forEach((el) => {
        el.hidden = true;
      });
    } catch (error) {
      status.textContent = `Failed to send: ${error.message}`;
      status.style.color = "#dc2626";
    } finally {
      sendButton.disabled = false;
      sendButton.textContent = "Send notification";
    }
  });
})();
