const Http = new XMLHttpRequest();

function onLoad() {
    loadSettings();
}

function loadSettings() {
    Http.open("GET", get_settings_url);
    Http.onreadystatechange = function() {
        if (Http.readyState === XMLHttpRequest.DONE && Http.status === 200) {
            response = JSON.parse(Http.responseText);

            document.getElementsByName('startAzm')[0].value = response['startAzm'];
            document.getElementsByName('endAzm')[0].value = response['endAzm'];
            document.getElementsByName('startAlt')[0].value = response['startAlt'];
            document.getElementsByName('endAlt')[0].value = response['endAlt'];
            document.getElementsByName('luxThresh')[0].value = response['luxThresh'];
            document.getElementsByName('conditionHistoryLength')[0].value = response['conditionHistoryLength'];

            document.getElementById('lastAzm').innerHTML = response['lastAzm'];
            document.getElementById('lastAlt').innerHTML = response['lastAlt'];
            document.getElementById('lastCondition').innerHTML = response['lastCondition'];
            document.getElementById('validateShadeState').innerHTML = response['validateShadeState'];
            document.getElementById('lastInArea').innerHTML = response['lastInArea'];
            
            if (response['commandOverride'] == 1) document.getElementById('override').checked = true;
            
            loadHistory();
        }
    }
    Http.send();
}

function loadHistory() {
    Http.open("GET", condition_history_url);
    Http.onreadystatechange = function() {
        if (Http.readyState === XMLHttpRequest.DONE && Http.status === 200) {
            response = JSON.parse(Http.responseText);

            let table = document.getElementById("historyTable");

            for (let row in response) {
                let newRow = table.insertRow(-1);
                let conditionCell = newRow.insertCell(0);
                let timestampCell = newRow.insertCell(1);

                conditionCell.innerHTML = response[row][0];
                timestampCell.innerHTML = response[row][1];
            }

            loadConditions();
        }
    }
    Http.send();
}

function loadConditions() {
    Http.open("GET", distinct_conditions_url);
    Http.onreadystatechange = function() {
        if (Http.readyState === XMLHttpRequest.DONE && Http.status === 200) {
            response = JSON.parse(Http.responseText);

            let closeBlindsSelect = document.getElementById("closeBlindsCon");
            let openBlindsSelect = document.getElementById("openBlindsCon");

            for (let row in response) {
                var opt = document.createElement('option');
                opt.value = response[row][0];
                opt.innerHTML = response[row][0];
                
                if (response[row][1] == "1") closeBlindsSelect.appendChild(opt); else openBlindsSelect.appendChild(opt);
            }
        }
    }
    Http.send();
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
    let commandOverride = document.getElementById('override').checked == true ? 1 : 0;

    let payload = {
        "startAzm":startAzm,
        "endAzm":endAzm,
        "startAlt":startAlt,
        "endAlt":endAlt,
        "conditionHistoryLength":conditionHistoryLength,
        "commandOverride":commandOverride,
        "luxThresh":luxThresh,
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

    Http.open("POST", save_settings_url);
    Http.setRequestHeader("Content-Type", "application/json");
    Http.onreadystatechange = function() {
        if (Http.readyState === XMLHttpRequest.DONE && Http.status === 200) {
            alert('Saved Successfully')
        }
    }
    Http.send(JSON.stringify(payload));
}