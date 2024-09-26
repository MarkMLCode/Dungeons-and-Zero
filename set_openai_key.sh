#!/bin/bash

read -p "Please enter the full OpenAI API key: " API_KEY

echo "export OPENAI_API_KEY=$API_KEY" >> ~/.bashrc

source ~/.bashrc

echo "The OPENAI_API_KEY has been set and will be available in future terminal sessions."