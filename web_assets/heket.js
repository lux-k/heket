async function showShareDialog(detectionId) {
//    document.getElementById("attachment_observation_id").value = observationId;
//    document.getElementById("attachment_observation_text").innerHTML = new Date(document.getElementById(observationId + "_ts").value).toLocaleString() + "<br>" + document.getElementById(observationId + "_blurb").innerHTML
//    await updateAttachmentList(observationId);
    await populateShareDialog(detectionId);
    document.getElementById("share_detection_dialog").showModal();
}

async function populateShareDialog(detectionId) {
    const res = await fetch("/api/detection/" + detectionId);
    const data = await res.json();

    const container_r = document.getElementById("share_detection_recips");
    container_r.innerHTML = "";

    data.shareable.forEach(entry => {
        container_r.innerHTML += `<input name="shareRecip" type="checkbox" value="${entry.value}">${entry.name}<br><small>&#9432; ${entry.warning}</small><br><br>`;
     });

    document.getElementById("share_detection_id").value = detectionId;

    const container = document.getElementById("share_detection_text");
    container.innerHTML = "";
   
    const div = document.createElement("div");

    div.className = "entry";
    div.innerHTML = `Labeled: ${data.label}<br>Species: ${data.species ?? "?"}<br>Captured: ${data.ts_formatted}<br><br><img src="/spectrogram/${data.detectionId}"><br><br><audio controls src=\"recordings/${data.file}\"></audio><br>`;
    container.appendChild(div);

    if (data.shared.length > 0) {
        data.shared.forEach(entry => {
            if (entry.url)
                container_r.innerHTML += `<a href="${entry.url}">${entry.name} (click to see)<br>`;
            else
                container_r.innerHTML += `${entry.name} (already shared)<br>`;
        });
    }

    if (container_r.innerHTML == "") 
        container_r.innerHTML = "No recipients available.";
 }

 async function shareDetection() {
     const checkedBoxes = document.querySelectorAll('input[name="shareRecip"]:checked');
    
    // Extract the values into a clean array
    const selectedValues = Array.from(checkedBoxes).map(cb => cb.value);
    const detectionId = document.getElementById("share_detection_id").value;

    await fetch('/api/detection/' + detectionId + '/share', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ recipients: selectedValues})
    });

    document.getElementById("share_detection_dialog").close();
}

function labelClip(file, label) {
    fetch('/label', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file, label })
    }).then(() => {
        location.reload(); // or remove row dynamically
    });
}

const preview = document.getElementById("spectrogram-preview");
const image = document.getElementById("spectrogram-image");
const weather = document.getElementById("weather");
const last_heard = document.getElementById("last-heard");
const playhead = document.getElementById("spectrogram-playhead");
var activeaudio = null;
var pinnedspectro = false;

document
.querySelectorAll(".detection-item")
.forEach(row => {
    row.addEventListener("mouseenter", e => {
        const eventId = row.dataset.eventId;
        image.src = "/spectrogram/" + eventId;
        preview.style.display = "block";
        preview.style.left = (e.pageX + 20) + "px";
        preview.style.top = (e.pageY + 30) + "px";
        if (activeaudio != null)
            activeaudio.removeEventListener("timeupdate",updatePlayhead)
        activeaudio = row.parentElement.querySelector("audio");
        activeaudio.addEventListener("timeupdate", updatePlayhead);

    });

    row.addEventListener("mouseleave", () => {
        if (!pinnedspectro)
            preview.style.display = "none";
    });

    row.addEventListener("click", () => {
        pinnedspectro = !pinnedspectro
    });
});


function updatePlayhead() {
    if (!activeaudio.duration)
        return;

    const x =
        (activeaudio.currentTime / activeaudio.duration) *
        image.clientWidth;

    playhead.style.left = `${x}px`;
}

document
.querySelectorAll(".weather-item")
.forEach(row => {
    row.addEventListener("mouseenter", e => {
        const eventId = row.dataset.eventId;
        weather.innerHTML = eventId
        weather.style.display = "block";
        weather.style.left = (e.pageX + 20) + "px";
        weather.style.top = (e.pageY + 30) + "px";
    });

    row.addEventListener("mouseleave", () => {
        weather.style.display = "none";
    });
});

document.querySelectorAll('fieldset legend').forEach(legend => {
  legend.addEventListener('click', () => {
    // Find the closest parent fieldset and toggle the class
    legend.closest('fieldset').classList.toggle('collapsed');
  });
});

const last_heard_things = [];
last_heard_update = 0;

async function updateSoundscapeHTML(data) {
    const max_msg = 10;
    try {
        if (data["last_update"] > last_heard_update) {
            const msg = data["label"] + " " + data["confidence"];
            last_heard.innerHTML = "&#x1F442 " + msg;
            last_heard_things.push(msg);
            if (last_heard_things.length > max_msg)
                last_heard_things.shift();
            
            last_heard.title = last_heard_things.toReversed().join("\\n");
            last_heard_update = data["last_update"];
        }
    } catch (err) {
        console.log(err);
    }
}

const toast = document.getElementById("toast");

var toastTimeout = setTimeout(() => {{
    if (toast) toast.style.display = "none";
    toastTimeout = null;
}}, 5000);

const evt = new EventSource('/event_stream');
evt.addEventListener('soundscape', (event) => {
    try {
        var data = JSON.parse(event.data);
        updateSoundscapeHTML(data);
    } catch (err) {
        console.log(err);
    }
});

evt.addEventListener('notification', (event) => {
    try {
        var data = JSON.parse(event.data);
        
        toast.style.display = "block";

        if (toastTimeout) {
            // it's already displayed... extend and add
            clearTimeout(toastTimeout)
            toast.innerHTML += data.message + "<br>";            
        } else {
            toast.innerHTML = data.message + "<br>";
        }

        toastTimeout = setTimeout(() => {{
            if (toast) toast.style.display = "none";
            toastTimeout = null;
        }}, 5000);        
    } catch (err) {
        console.log(err);
    }
});
// to make sure the browser releases the SSE connection
window.addEventListener("pagehide", () => {
    evt.close();
});