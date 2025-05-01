function onLoad() {
    new Promise((resolve, reject) => {
            console.log("Loading app data");
            resolve();
        })
        .then(loadSettings)
        .then(loadHistory)
        .then(loadConditions)
        .then(loadTicktockStatus)
        .then(() => {console.log("done")})
}

function makeHttpRequest(method, url, callback, payload) {
    const Http = new XMLHttpRequest();
    Http.open(method, url);
    if (method == "POST") {
        Http.setRequestHeader("Content-Type", "application/json");
    }
    Http.onreadystatechange = function() {
        if (Http.readyState === XMLHttpRequest.DONE && Http.status === 200) {
            callback(JSON.parse(Http.responseText));
        }
    }
    Http.send(payload);
}

function loadSettings() {
    makeHttpRequest("GET", get_settings_url, (response) => {
        document.getElementsByName('startAzm')[0].value = response['startAzm'];
        document.getElementsByName('endAzm')[0].value = response['endAzm'];
        document.getElementsByName('startAlt')[0].value = response['startAlt'];
        document.getElementsByName('endAlt')[0].value = response['endAlt'];
        document.getElementsByName('luxThresh')[0].value = response['luxThresh'];
        document.getElementsByName('solarThresh')[0].value = response['solarThresh'];
        document.getElementsByName('conditionHistoryLength')[0].value = response['conditionHistoryLength'];
        document.getElementsByName('changeBufferDurationSec')[0].value = response['changeBufferDurationSec'];
        document.getElementsByName('upperAlt')[0].value = response['upperAlt'];
        document.getElementsByName('lowerAlt')[0].value = response['lowerAlt'];
        document.getElementsByName('upperAltPer')[0].value = response['upperAltPer'];
        document.getElementsByName('lowerAltPer')[0].value = response['lowerAltPer'];
        document.getElementsByName('ticktockInterval')[0].value = response['ticktockInterval'];

        document.getElementById('lastAzm').innerHTML = response['lastAzm'];
        document.getElementById('lastAlt').innerHTML = response['lastAlt'];
        document.getElementById('lastCondition').innerHTML = response['lastCondition'];
        document.getElementById('validateShadeState').innerHTML = response['validateShadeState'];
        document.getElementById('lastInArea').innerHTML = response['lastInArea'];
        document.getElementById('lastChangeDate').innerHTML = new Date(response['lastChangeDate'] * 1000);
        
        if (response['commandOverride'] == 1) document.getElementById('override').checked = true;
    });
}

function loadHistory() {
    makeHttpRequest("GET", condition_history_url, (response) => {
        let table = document.getElementById("historyTable");

        for (let row in response) {
            let newRow = table.insertRow(-1);
            let conditionCell = newRow.insertCell(0);
            let timestampCell = newRow.insertCell(1);

            conditionCell.innerHTML = response[row][0];
            timestampCell.innerHTML = response[row][1];
        }
    });
}

function loadConditions() {
    makeHttpRequest("GET", distinct_conditions_url, (response) => {
        let closeBlindsSelect = document.getElementById("closeBlindsCon");
        let openBlindsSelect = document.getElementById("openBlindsCon");

        for (let row in response) {
            var opt = document.createElement('option');
            opt.value = response[row][0];
            opt.innerHTML = response[row][0];
            
            if (response[row][1] == "1") closeBlindsSelect.appendChild(opt); else openBlindsSelect.appendChild(opt);
        }
    });
}

function loadTicktockStatus() {
    makeHttpRequest("GET", ticktock_status_url, (response) => {
        document.getElementById("tickTock").innerHTML = response["status"];
    });
}

function moveToOpen() {
    let closedBlindsSel = document.getElementById('closeBlindsCon');
    let openBlindsSel = document.getElementById('openBlindsCon');

    for (let option = closedBlindsSel.length - 1; option > -1 ; option--) {
        if (closedBlindsSel[option].selected) {
            openBlindsSel.appendChild(closedBlindsSel[option]);
        }
    }
}

function moveToClose() {
    let closedBlindsSel = document.getElementById('closeBlindsCon');
    let openBlindsSel = document.getElementById('openBlindsCon');

    for (let option = openBlindsSel.length - 1; option > -1 ; option--) {
        if (openBlindsSel[option].selected) {
            closedBlindsSel.appendChild(openBlindsSel[option]);
        }
    }
}

function saveSettings() {
    let startAzm = document.getElementsByName('startAzm')[0].value;
    let endAzm = document.getElementsByName('endAzm')[0].value;
    let startAlt = document.getElementsByName('startAlt')[0].value;
    let endAlt = document.getElementsByName('endAlt')[0].value;
    let conditionHistoryLength = document.getElementsByName('conditionHistoryLength')[0].value;
    let luxThresh = document.getElementsByName('luxThresh')[0].value;
    let solarThresh = document.getElementsByName('solarThresh')[0].value;
    let changeBufferDurationSec = document.getElementsByName('changeBufferDurationSec')[0].value;
    let upperAlt = document.getElementsByName('upperAlt')[0].value;
    let lowerAlt = document.getElementsByName('lowerAlt')[0].value;
    let upperAltPer = document.getElementsByName('upperAltPer')[0].value;
    let lowerAltPer = document.getElementsByName('lowerAltPer')[0].value;
    let ticktockInterval = document.getElementsByName('ticktockInterval')[0].value;
    let commandOverride = document.getElementById('override').checked == true ? 1 : 0;

    let payload = {
        "startAzm":startAzm,
        "endAzm":endAzm,
        "startAlt":startAlt,
        "endAlt":endAlt,
        "conditionHistoryLength":conditionHistoryLength,
        "commandOverride":commandOverride,
        "luxThresh":luxThresh,
        "solarThresh":solarThresh,
        "changeBufferDurationSec":changeBufferDurationSec,
        "upperAlt":upperAlt,
        "lowerAlt":lowerAlt,
        "upperAltPer":upperAltPer,
        "lowerAltPer":lowerAltPer,
        "ticktockInterval":ticktockInterval,
        "distinctConditions":{}
    };
    
    let closedBlindsSel = document.getElementById('closeBlindsCon');
    let openBlindsSel = document.getElementById('openBlindsCon');

    for (let option = openBlindsSel.length - 1; option > -1 ; option--) {
        payload['distinctConditions'][openBlindsSel[option].value] = 0;
    }

    for (let option = closedBlindsSel.length - 1; option > -1 ; option--) {
        payload['distinctConditions'][closedBlindsSel[option].value] = 1;
    }

    makeHttpRequest("POST", save_settings_url, (response) => {
        alert('Saved Successfully');
    }, JSON.stringify(payload));
}

function startTicktock() {
    makeHttpRequest("GET", ticktock_start_url, (response => {
        if (response['status'] == "success") {
            loadTicktockStatus();
        }
    }));
}

function stopTicktock() {
    makeHttpRequest("GET", ticktock_stop_url, (response => {
        if (response['status'] == "success") {
            loadTicktockStatus();
        }
    }));
}