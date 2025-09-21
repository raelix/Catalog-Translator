var transteArray = [];

async function translateSelected(authKey, selectList) {
    const collection = await stremioAddonCollectionGet(authKey);
    var addons = [];

    for(var i=0; i<collection.result.addons.length; i++) {
        addons.push({
            "manifest": collection.result.addons[i].manifest,
            "transportUrl": collection.result.addons[i].transportUrl,
            "flags": {
                "official": false,
                "protected": false
            }
        });
    }

    for(var j=0; j<selectList.length; j++) {
        for(var i=0; i<addons.length; i++) {
            if (selectList[j].id == addons[i].manifest.id) {
                var addonUrl = generateTranslatorLink(addons[i].transportUrl, selectList[j].skipPoster, selectList[j].toastRatings);
                var response = await fetch(addonUrl);
                var tranlatorManifest = await response.json();
                addons[i] = {
                    "manifest": tranlatorManifest,
                    "transportUrl": addonUrl,
                    "flags": {
                        "official": false,
                        "protected": false
                    }
                };
                break;
            }
        }
        // Add new addon
        var addonUrl = generateTranslatorLink(selectList[j].transportUrl, selectList[j].skipPoster, selectList[j].toastRatings);
        var response = await fetch(addonUrl);
        var tranlatorManifest = await response.json();
        addons[i] = {
            "manifest": tranlatorManifest,
            "transportUrl": addonUrl,
            "flags": {
                "official": false,
                "protected": false
            }
        };
    }

    var resp = await stremioAddonCollectionSet(authKey, addons);
    if (resp.result.success == true) {
        alert("Addon installati correttamente!")
        //Refresh addons
        await reloadAddons(authKey);
    }
}

async function reloadAddons(authKey) {
    transteArray = [];
    const addons = document.querySelectorAll(".addon-info");
    addons.forEach(addon => addon.remove());
    await stremioLoadAddons(authKey);
}

function generateTranslatorLink(addonUrl, skip_poster, toast_ratings) {
    const serverUrl = window.location.origin;
    const baseAddonUrl = getBaseUrl(addonUrl).replace("/manifest.json", "");
    const urlEncoded = btoa(baseAddonUrl);
    const userSettings = `sp=${skip_poster},tr=${toast_ratings}`;
    
    if (addonUrl.includes(serverUrl)) {
        const addonBase64String = addonUrl.split("/")[3];
        return `${serverUrl}/${addonBase64String}/${userSettings}/manifest.json`;
    }

    return `${serverUrl}/${urlEncoded}/${userSettings}/manifest.json`;
}

function getBaseUrl(urlString) {
    const url = new URL(urlString);
    return `${url.protocol}//${url.host}${url.pathname}`;
}
