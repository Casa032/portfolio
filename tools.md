---
layout: default
title: Projects by tool
---

<section class="tools-page">
    <h1>Projects by tool</h1>

    {% assign all_tools = "" | split: "" %}
    {% for project in site.projects %}
        {% for tool in project.tools %}
            {% assign all_tools = all_tools | push: tool %}
        {% endfor %}
    {% endfor %}
    {% assign unique_tools = all_tools | uniq | sort %}

    {% for tool in unique_tools %}
    <div class="tool-group" id="{{ tool | slugify }}">
        <h2>{{ tool }}</h2>
        <div class="projects-list">
            {% for project in site.projects %}
                {% if project.tools contains tool %}
                <a href="{{ project.url | relative_url }}" class="project">
                    <h3>{{ project.title }}</h3>
                    <p class="project-tech">{{ project.tech }}</p>
                </a>
                {% endif %}
            {% endfor %}
        </div>
    </div>
    {% endfor %}
</section>