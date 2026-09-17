// Wait until the whole page is loaded before running
document.addEventListener('DOMContentLoaded', function () {

    // Find every element with the class "skill"
    var skills = document.querySelectorAll('.skill');

    // Go through each skill one by one
    skills.forEach(function (skill) {

        // Read the data-percent value from this skill
        var percent = skill.getAttribute('data-percent');

        // Find the blue fill bar inside this skill
        var bar = skill.querySelector('.skill-bar');

        // Set its width to the percent, which triggers the CSS animation
        bar.style.width = percent + '%';
    });

});