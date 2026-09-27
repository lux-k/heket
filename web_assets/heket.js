var detectionChanged = false;

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
        container_r.innerHTML += `<input id="shareRecip-${entry.value}" class="${entry.class ?? ""}" name="shareRecip" type="checkbox" value="${entry.value}">${entry.name}<br><small>&#9432; ${entry.warning}</small><br><br>`;
     });

    document.getElementById("share_detection_id").value = detectionId;

    const container = document.getElementById("share_detection_text");
    container.innerHTML = "";
   
    const div = document.createElement("div");

    div.className = "entry";
    div.innerHTML = `Label: `;
    var h = "";
    h += "<select id=\"share_label_select\">";
    data.labels.forEach( entry => {
        h += `<option value="${entry.species ?? "?"}">${entry.label}</option>`;
    });
    h += "</select><br>";

    div.innerHTML += h;
    
    div.innerHTML += `Species: <div id="share_species" style="display: inline"></div><br>Captured: ${data.ts_formatted}<br><br><img src="/spectrogram/${data.detectionId}"><br><br><audio controls src=\"recordings/${data.file}\"></audio><br>`;
    
    container.appendChild(div);
    
    var f = function() {
        var val = document.getElementById('share_label_select').value;
        
        if (val === "?")
            document.querySelectorAll('.share-requires-species').forEach(
                entry => {entry.checked = false; entry.disabled = true;}
            ); 
        else {
            document.querySelectorAll('.share-requires-species').forEach(
                entry => {entry.disabled = false;}
            ); 
        }
        document.getElementById('share_species').innerHTML = document.getElementById('share_label_select').value ?? "?";
        
    };


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

    document.getElementById('share_label_select').addEventListener("change", f);
    f();

}

 async function shareDetection() {
     const checkedBoxes = document.querySelectorAll('input[name="shareRecip"]:checked');
    
    // Extract the values into a clean array
    const selectedValues = Array.from(checkedBoxes).map(cb => cb.value);
    const detectionId = document.getElementById("share_detection_id").value;
    const labelSelect = document.getElementById("share_label_select");
    const label = labelSelect.options[labelSelect.selectedIndex].text;

    await fetch('/api/detection/' + detectionId + '/share', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ recipients: selectedValues, label: label})
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
const labels = document.getElementById("spectrogram-labels");
const weather = document.getElementById("weather");
const last_heard = document.getElementById("last-heard");
const playhead = document.getElementById("spectrogram-playhead");
var activeaudio = null;
var pinnedspectro = false;

document.getElementById('slice-save-label-button').addEventListener("click", async function () {

    const activeSlice = document.querySelector(".spectrogram-slice.active");

    if (!activeSlice) {
        return;
    }

    const sliceId = activeSlice.dataset.sliceId;
    const detectionId = activeSlice.dataset.detectionId;
    
    const newLabel = document.getElementById("slice-label").value;
    activeSlice.textContent = newLabel + "\n✅";
    
    const data = new FormData();
    data.append("label", newLabel);

    const res = await fetch("/api/detections/" + detectionId + "/slice/"+ sliceId, {
        method: "PATCH",
        body: data
    });
    detectionChanged = true;
});

async function save_slice_curation() {
    const activeSlice = document.querySelector(".spectrogram-slice.active");

    if (!activeSlice) {
        return;
    }

    const sliceId = activeSlice.dataset.sliceId;
    const detectionId = activeSlice.dataset.detectionId;

    const newCuration = document.getElementById("slice-curation").value;
    console.log(sliceId, newCuration);
    
    const data = new FormData();
    data.append("curation", newCuration);

    const res = await fetch("/api/detections/" + detectionId + "/slice/"+ sliceId, {
        method: "PATCH",
        body: data
    });
    detectionChanged = true;    
}

var end = 0;

document.getElementById('slice-replay-button').addEventListener("click", async function () {
    const activeSlice = document.querySelector(".spectrogram-slice.active");

    if (!activeSlice) {
        return;
    }

    const isPlaying = activeaudio && !activeaudio.paused && !activeaudio.ended && activeaudio.readyState > 2;
    if (isPlaying) {
        //this.textContent = "▶";
        end = 0;
        stopAtEnd();
    } else {
//        this.textContent = "◼";
        playSlice(parseFloat(activeSlice.dataset.audioOffset), parseFloat(activeSlice.dataset.audioDuration));
    }
});

function playSlice(offset, duration) {
    end = offset + duration;

    activeaudio.currentTime = offset;
    activeaudio.play();

    activeaudio.addEventListener("timeupdate", stopAtEnd);
}

function stopAtEnd() {
    if (activeaudio.currentTime >= end || end == 0) {
        activeaudio.pause();
        activeaudio.removeEventListener("timeupdate", stopAtEnd);
//        document.getElementById('slice-replay-button').textContent = "▶";
    }
}

document
.querySelectorAll(".detection-item")
.forEach(row => {
    row.addEventListener("mouseenter", async e => {
        const eventId = row.dataset.eventId;
        image.src = "/spectrogram/" + eventId;
        preview.style.display = "block";
        preview.style.left = (e.pageX + 20) + "px";
        preview.style.top = (e.pageY + 30) + "px";
        if (activeaudio != null) {
            activeaudio.removeEventListener("timeupdate",updatePlayhead)
            activeaudio.removeEventListener("timeupdate", stopAtEnd);
        }

        activeaudio = row.parentElement.querySelector("audio");
        activeaudio.addEventListener("timeupdate", updatePlayhead);
  
        const res = await fetch("/api/detections/" + eventId + "/slices");
        const slices = await res.json();

        const detectionDuration = slices.duration;

        labels.innerHTML = "";
        const form = document.getElementById("spectrogram-label-update");
        form.style.display = "none";

        for (const slice of slices.slices) {
            const box = document.createElement("div");
            var current_label = ""
            box.className = "spectrogram-slice";
            if (slice.labeled != null) {
                box.textContent = slice.labeled + "\n✅";
                current_label = slice.labeled
            } else {
                box.textContent = slice.prediction + "\n(" + slice.confidence.toFixed(2) + ")";
                current_label = slice.prediction
            }

            box.dataset.sliceId = slice.slice_id;
            box.dataset.detectionId = eventId
            box.dataset.audioOffset = slice.offset;
            box.dataset.audioDuration = slice.duration;

            box.style.left =
                `${(slice.offset / detectionDuration) * 100}%`;

            box.style.width =
                `${(slice.duration / detectionDuration) * 100}%`;

            box.addEventListener("click", function () {

                document.querySelectorAll(".spectrogram-slice").forEach(slice => {
                    slice.classList.remove("active");
                });

                this.classList.add("active");

                const form = document.getElementById("spectrogram-label-update");
                document.getElementById("slice-label").value = current_label;
                document.getElementById("slice-curation").value = slice.curation ?? "";
                document.getElementById("slice-model-prediction").textContent = slice.prediction + " ("  + slice.confidence.toFixed(2) + ")";
                form.style.display = "block";
            });

            labels.appendChild(box);
        }
    });

    row.addEventListener("mouseleave", () => {
        if (!pinnedspectro)
            preview.style.display = "none";
        if (detectionChanged) 
            location.reload();
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