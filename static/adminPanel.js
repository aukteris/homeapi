const Http = new XMLHttpRequest();

function onLoad() {
    loadSettings(loadHistory);
}

function loadSettings(cb) {
    Http.open("GET", get_settings_url);
    Http.onreadystatechange = function() {
        if (Http.readyState === XMLHttpRequest.DONE && Http.status === 200) {
            response = JSON.parse(Http.responseText);

            document.getElementsByName('startAzm')[0].value = response['startAzm'];
            document.getElementsByName('endAzm')[0].value = response['endAzm'];
            document.getElementsByName('startAlt')[0].value = response['startAlt'];
            document.getElementsByName('endAlt')[0].value = response['endAlt'];
            document.getElementsByName('conditionHistoryLength')[0].value = response['conditionHistoryLength'];

            document.getElementById('lastAzm').innerHTML = response['lastAzm'];
            document.getElementById('lastAlt').innerHTML = response['lastAlt'];
            document.getElementById('lastCondition').innerHTML = response['lastCondition'];
            document.getElementById('validateShadeState').innerHTML = response['validateShadeState'];
            document.getElementById('lastInArea').innerHTML = response['lastInArea'];
            cb();
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

        }
    }
    Http.send();
}

function saveSettings() {
    let startAzm = document.getElementsByName('startAzm')[0].value;
    let endAzm = document.getElementsByName('endAzm')[0].value;
    let startAlt = document.getElementsByName('startAlt')[0].value;
    let endAlt = document.getElementsByName('endAlt')[0].value;
    let conditionHistoryLength = document.getElementsByName('conditionHistoryLength')[0].value;

    let queryString = `?startAzm=${startAzm}&endAzm=${endAzm}&startAlt=${startAlt}&endAlt=${endAlt}&conditionHistoryLength=${conditionHistoryLength}`
    let full_save_settings_url = save_settings_url + queryString;

    Http.open("GET", full_save_settings_url);
    Http.onreadystatechange = function() {
        if (Http.readyState === XMLHttpRequest.DONE && Http.status === 200) {
            alert('Saved Successfully')
        }
    }
    Http.send();
}